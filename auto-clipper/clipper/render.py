"""Download segments and render vertical 1080x1920 Shorts with burned-in captions."""
from pathlib import Path

from .util import run, ytdlp_base

VIDEO_FMT = "bv*[height<=1080]+ba/b[height<=1080]/best"


def download_audio(url: str, out_base: Path) -> Path:
    run(ytdlp_base() + ["-f", "Audio_Only/ba/worstaudio/worst", "-o", f"{out_base}.%(ext)s", url])
    return next(p for p in out_base.parent.glob(out_base.name + ".*") if not p.name.endswith(".part"))


def download_video(url: str, out_base: Path, start: float | None = None, end: float | None = None) -> Path:
    cmd = ytdlp_base() + ["-f", VIDEO_FMT, "--merge-output-format", "mp4", "-o", f"{out_base}.%(ext)s"]
    if start is not None and end is not None:
        cmd += ["--download-sections", f"*{start:.2f}-{end:.2f}", "--force-keyframes-at-cuts"]
    run(cmd + [url])
    return next(p for p in out_base.parent.glob(out_base.name + ".*") if not p.name.endswith(".part"))


def render_short(src: Path, out: Path, max_len: float, layout: str, ass: Path | None) -> Path:
    if layout == "fill":
        chain = "[0:v]scale=-2:1920,crop=1080:1920,setsar=1"
    else:  # fit: gameplay centred over a blurred, zoomed copy of itself
        chain = ("[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                 "boxblur=24:2,eq=brightness=-0.08[bg];[b]scale=1080:-2[fg];"
                 "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    if ass is not None:
        chain += f",ass={ass.name}"
    chain += ",fps=30[v]"
    run(["ffmpeg", "-y", "-v", "error", "-i", src.name, "-t", f"{max_len:.2f}", "-filter_complex", chain,
         "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart",
         str(out.resolve())], cwd=src.parent)
    return out
