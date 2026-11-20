import json
import os
import subprocess
from pathlib import Path


def log(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    log("$ " + " ".join(cmd))
    return subprocess.run(cmd, check=True, **kw)


def ytdlp_base() -> list[str]:
    cmd = ["yt-dlp", "--no-progress", "--no-warnings", "--retries", "5"]
    cookies = os.environ.get("YTDLP_COOKIES_FILE")
    if cookies and Path(cookies).is_file():
        cmd += ["--cookies", cookies]
    return cmd


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(json.loads(out)["format"].get("duration") or 0)
