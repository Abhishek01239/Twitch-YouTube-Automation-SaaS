"""Discover source material: Twitch clips, Twitch VODs and YouTube videos."""
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests

from .util import log, ytdlp_base


@dataclass
class Source:
    id: str                 # unique key used for de-duplication
    kind: str               # "clip" (already a highlight) or "long" (needs highlight search)
    url: str
    title: str
    creator: str
    duration: float = 0.0
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------- Twitch

class Twitch:
    def __init__(self) -> None:
        self.client_id = os.environ.get("TWITCH_CLIENT_ID", "")
        secret = os.environ.get("TWITCH_CLIENT_SECRET", "")
        if not self.client_id or not secret:
            raise RuntimeError("TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET are required for Twitch sources")
        r = requests.post("https://id.twitch.tv/oauth2/token", data={
            "client_id": self.client_id, "client_secret": secret, "grant_type": "client_credentials",
        }, timeout=30)
        r.raise_for_status()
        self.token = r.json()["access_token"]

    def get(self, path: str, params) -> list[dict]:
        r = requests.get(f"https://api.twitch.tv/helix/{path}", params=params, timeout=30,
                         headers={"Client-Id": self.client_id, "Authorization": f"Bearer {self.token}"})
        r.raise_for_status()
        return r.json().get("data", [])

    def user_id(self, login: str) -> str | None:
        users = self.get("users", {"login": login.strip().lower()})
        return users[0]["id"] if users else None


def _parse_twitch_duration(s: str) -> float:
    total, num = 0, ""
    for ch in s:
        if ch.isdigit():
            num += ch
        else:
            total += int(num or 0) * {"h": 3600, "m": 60, "s": 1}.get(ch, 0)
            num = ""
    return float(total)


def twitch_clip_sources(cfg: dict, tw: Twitch) -> list[Source]:
    out: list[Source] = []
    started = (datetime.now(timezone.utc) - timedelta(hours=cfg.get("period_hours", 24))).isoformat()
    for login in cfg.get("channels") or []:
        uid = tw.user_id(login)
        if not uid:
            log(f"[twitch] unknown channel {login}")
            continue
        clips = tw.get("clips", {"broadcaster_id": uid, "started_at": started, "first": 50})
        clips = [c for c in clips if c.get("view_count", 0) >= cfg.get("min_views", 0)]
        clips.sort(key=lambda c: c.get("view_count", 0), reverse=True)
        for c in clips[: cfg.get("max_per_channel", 3)]:
            out.append(Source(id=f"twitch-clip:{c['id']}", kind="clip", url=c["url"],
                              title=c.get("title") or f"{c['broadcaster_name']} clip",
                              creator=c["broadcaster_name"], duration=float(c.get("duration", 0)),
                              extra={"views": c.get("view_count", 0)}))
    log(f"[twitch] {len(out)} clip candidates")
    return out


def twitch_vod_sources(cfg: dict, tw: Twitch) -> list[Source]:
    out: list[Source] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cfg.get("max_age_hours", 48))
    for login in cfg.get("channels") or []:
        uid = tw.user_id(login)
        if not uid:
            log(f"[twitch] unknown channel {login}")
            continue
        vods = tw.get("videos", {"user_id": uid, "type": "archive", "first": 10})
        n = 0
        for v in vods:
            created = datetime.fromisoformat(v["created_at"].replace("Z", "+00:00"))
            if created < cutoff or n >= cfg.get("max_vods_per_channel", 1):
                continue
            n += 1
            out.append(Source(id=f"twitch-vod:{v['id']}", kind="long", url=v["url"], title=v.get("title") or "",
                              creator=v.get("user_name") or login,
                              duration=_parse_twitch_duration(v.get("duration", ""))))
    log(f"[twitch] {len(out)} VOD candidates")
    return out


# ---------------------------------------------------------------- YouTube / any yt-dlp URL

def _ytdlp_json(url: str, flat: bool, limit: int | None = None) -> dict:
    cmd = ytdlp_base() + ["-J"]
    if flat:
        cmd += ["--flat-playlist"]
    if limit:
        cmd += ["--playlist-end", str(limit)]
    res = subprocess.run(cmd + [url], check=True, capture_output=True, text=True)
    return json.loads(res.stdout)


def url_source(url: str) -> Source:
    info = _ytdlp_json(url, flat=False)
    dur = float(info.get("duration") or 0)
    kind = "clip" if dur and dur <= 75 else "long"
    return Source(id=f"{info.get('extractor_key', 'url').lower()}:{info['id']}", kind=kind,
                  url=info.get("webpage_url") or url, title=info.get("title") or "",
                  creator=info.get("uploader") or info.get("channel") or "", duration=dur)


def youtube_sources(cfg: dict) -> list[Source]:
    out: list[Source] = []
    for url in cfg.get("urls") or []:
        try:
            if "watch?v=" in url or "youtu.be/" in url or "/shorts/" in url or "/live/" in url:
                out.append(url_source(url))
                continue
            listing = _ytdlp_json(url, flat=True, limit=cfg.get("max_videos", 1) + 5)
            n = 0
            for e in listing.get("entries") or []:
                if n >= cfg.get("max_videos", 1):
                    break
                if e.get("live_status") in ("is_live", "is_upcoming"):
                    continue
                vid_url = e.get("url") or f"https://www.youtube.com/watch?v={e['id']}"
                out.append(url_source(vid_url))
                n += 1
        except subprocess.CalledProcessError as exc:
            log(f"[youtube] failed to read {url}: {exc.stderr[-500:] if exc.stderr else exc}")
    log(f"[youtube] {len(out)} candidates")
    return out


def discover(cfg: dict) -> list[Source]:
    sources: list[Source] = []
    scfg = cfg.get("sources", {})
    tc, tv = scfg.get("twitch_clips", {}), scfg.get("twitch_vods", {})
    if (tc.get("channels") or tv.get("channels")):
        try:
            tw = Twitch()
            if tc.get("channels"):
                sources += twitch_clip_sources(tc, tw)
            if tv.get("channels"):
                sources += twitch_vod_sources(tv, tw)
        except Exception as exc:  # keep going with other sources
            log(f"[twitch] error: {exc}")
    if scfg.get("youtube", {}).get("urls"):
        sources += youtube_sources(scfg["youtube"])
    return sources
