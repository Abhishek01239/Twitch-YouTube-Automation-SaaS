"""Entry point: discover -> find highlights -> render captioned Shorts -> schedule on Zernio."""
import argparse
import json
import os
import re
import shutil
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import captions, highlights, render
from .sources import Source, discover, url_source
from .util import log, probe_duration

ROOT = Path(__file__).resolve().parent.parent
MAX_FAILURES = 3


def load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"processed": {}, "last_scheduled": None}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-")[:60] or "clip"


def make_clips(src: Source, cfg: dict, work: Path, out_dir: Path) -> list[dict]:
    c = cfg["clips"]
    work.mkdir(parents=True, exist_ok=True)
    segments: list[tuple[Path, float]] = []
    if src.kind == "clip":
        f = render.download_video(src.url, work / "clip")
        segments.append((f, min(probe_duration(f), 60.0)))
    else:
        audio = render.download_audio(src.url, work / "audio")
        db = highlights.loudness_per_second(audio)
        moments = highlights.pick_moments(db, int(c["length"]), int(c["lead_in"]), int(c["per_video"]), float(c["min_score"]))
        audio.unlink(missing_ok=True)
        for i, (start, end, _) in enumerate(moments):
            f = render.download_video(src.url, work / f"seg{i}", start, end)
            segments.append((f, end - start))
    return _render_segments(segments, src, cfg, out_dir)


def build_post(meta: dict, media_url: str, when: datetime, pcfg: dict) -> dict:
    fields = {"title": (meta["title"] or "Gameplay highlight").strip(), "creator": meta["creator"],
              "source_url": meta["source_url"]}
    title = pcfg.get("title_template", "{title}").format(**fields)[:100]
    desc = pcfg.get("description_template", "{title}").format(**fields).strip()
    yt = pcfg.get("youtube", {})
    platforms = []
    for acc in pcfg["accounts"]:
        entry = {"platform": acc["platform"], "accountId": acc["account_id"]}
        if acc["platform"] == "youtube":
            entry["platformSpecificData"] = {"title": title, "visibility": yt.get("visibility", "public"),
                                             "categoryId": str(yt.get("category_id", "20")),
                                             "madeForKids": bool(yt.get("made_for_kids", False))}
        platforms.append(entry)
    return {"content": desc, "tags": pcfg.get("tags", []), "mediaItems": [{"type": "video", "url": media_url}],
            "platforms": platforms, "scheduledFor": when.strftime("%Y-%m-%dT%H:%M:%SZ")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--state", default=str(ROOT / "state" / "state.json"))
    ap.add_argument("--url", help="Clip this single video/clip URL instead of configured sources")
    ap.add_argument("--file", help="Clip a local video file (testing)")
    ap.add_argument("--dry-run", action="store_true", default=os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes"))
    ap.add_argument("--max-posts", type=int)
    ap.add_argument("--out", default=str(ROOT / "output"))
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    pcfg = cfg["posting"]
    state_path = Path(args.state)
    state = load_state(state_path)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    work_root = ROOT / "work"
    max_posts = args.max_posts or int(pcfg.get("max_posts_per_run", 3))
    log(f"mode: {'DRY RUN (nothing will be posted)' if args.dry_run else 'LIVE (posting via Zernio)'}")

    if args.file:
        f = Path(args.file).resolve()
        sources = [Source(id=f"file:{f.stem}", kind="long" if probe_duration(f) > 75 else "clip",
                          url=f.as_uri(), title=f.stem, creator="local")]
    elif args.url:
        sources = [url_source(args.url)]
    else:
        sources = discover(cfg)

    processed = state.setdefault("processed", {})
    todo = [s for s in sources if processed.get(s.id, {}).get("status") != "done"
            and processed.get(s.id, {}).get("failures", 0) < MAX_FAILURES]
    log(f"{len(sources)} sources found, {len(todo)} new")

    clips: list[dict] = []
    for src in todo:
        if len(clips) >= max_posts:
            break
        log(f"\n=== {src.id}: {src.title!r} by {src.creator} ({src.kind}, {src.duration:.0f}s)")
        work = work_root / slug(src.id)
        try:
            if args.file:  # local files: yt-dlp can't fetch file:// so copy in place
                work.mkdir(parents=True, exist_ok=True)
                local = Path(args.file).resolve()
                if src.kind == "clip":
                    shutil.copy(local, work / "clip.mp4")
                    made = _local_clip(work / "clip.mp4", src, cfg, out_dir)
                else:
                    made = _local_long(local, src, cfg, work, out_dir)
            else:
                made = make_clips(src, cfg, work, out_dir)
            for m in made:
                m["_source"] = src.id
            clips += made
            processed[src.id] = {"status": "rendered", "at": datetime.now(timezone.utc).isoformat(), "clips": len(made)}
            if not made:
                processed[src.id]["status"] = "done"  # nothing hype enough; don't retry
        except Exception as exc:
            traceback.print_exc()
            entry = processed.setdefault(src.id, {})
            entry["failures"] = entry.get("failures", 0) + 1
            entry["last_error"] = str(exc)[-300:]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    clips = clips[:max_posts]
    now = datetime.now(timezone.utc)
    when = now + timedelta(minutes=int(pcfg.get("first_delay_minutes", 20)))
    gap = timedelta(minutes=int(pcfg.get("gap_minutes", 120)))
    if state.get("last_scheduled"):
        when = max(when, datetime.fromisoformat(state["last_scheduled"]) + gap)

    zernio = None
    if clips and not args.dry_run:
        from .zernio import Zernio
        zernio = Zernio()

    posted_sources: set[str] = set()
    failed_sources: set[str] = set()
    for meta in clips:
        path = out_dir / meta["file"]
        if args.dry_run:
            body = build_post(meta, "<uploaded-url>", when, pcfg)
            log(f"[dry-run] would schedule {meta['file']} at {body['scheduledFor']}: {body['platforms'][0].get('platformSpecificData', {}).get('title', '')}")
        else:
            try:
                media_url = zernio.upload(path)
                body = build_post(meta, media_url, when, pcfg)
                key = str(uuid.uuid5(uuid.NAMESPACE_URL, meta["clip_id"]))
                resp = zernio.create_post(body, key)
                post_id = (resp.get("post") or {}).get("_id")
                log(f"[zernio] scheduled {meta['file']} for {body['scheduledFor']} (post {post_id})")
                state["last_scheduled"] = when.isoformat()
                posted_sources.add(meta["_source"])
            except Exception as exc:
                traceback.print_exc()
                failed_sources.add(meta["_source"])
                processed[meta["_source"]]["last_error"] = str(exc)[-300:]
                continue
        when += gap

    for sid in posted_sources - failed_sources:
        processed[sid]["status"] = "done"
    for sid in failed_sources:
        processed[sid]["failures"] = processed[sid].get("failures", 0) + 1

    if args.dry_run:
        log(f"\nDry run finished: {len(clips)} clip(s) in {out_dir}. State not saved.")
    else:
        save_state(state_path, state)
        log(f"\nDone: {len(posted_sources - failed_sources)} source(s) posted, {len(failed_sources)} failed.")


def _local_clip(f: Path, src: Source, cfg: dict, out_dir: Path) -> list[dict]:
    return _render_segments([(f, min(probe_duration(f), 60.0))], src, cfg, out_dir)


def _local_long(local: Path, src: Source, cfg: dict, work: Path, out_dir: Path) -> list[dict]:
    import subprocess
    c = cfg["clips"]
    db = highlights.loudness_per_second(local)
    moments = highlights.pick_moments(db, int(c["length"]), int(c["lead_in"]), int(c["per_video"]), float(c["min_score"]))
    segs = []
    for i, (start, end, _) in enumerate(moments):
        seg = work / f"seg{i}.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-i", str(local), "-t", str(end - start),
                        "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(seg)], check=True)
        segs.append((seg, end - start))
    return _render_segments(segs, src, cfg, out_dir)


def _render_segments(segs, src: Source, cfg: dict, out_dir: Path) -> list[dict]:
    c = cfg["clips"]
    results = []
    for i, (seg, length) in enumerate(segs):
        ass = None
        if c.get("captions", True):
            words = captions.transcribe_words(seg, c.get("whisper_model", "base"), c.get("language"))
            if words:
                ass = seg.with_suffix(".ass")
                captions.write_ass(words, ass)
        name = f"{slug(src.creator)}-{slug(src.id)}-{i}"
        out = render.render_short(seg, out_dir / f"{name}.mp4", length, c.get("layout", "fit"), ass)
        meta = {"clip_id": f"{src.id}#{i}", "source_id": src.id, "source_url": src.url, "title": src.title,
                "creator": src.creator, "file": out.name, "duration": round(probe_duration(out), 2)}
        (out_dir / f"{name}.json").write_text(json.dumps(meta, indent=2))
        results.append(meta)
        log(f"[render] {out.name} ({meta['duration']}s)")
    return results


if __name__ == "__main__":
    main()
