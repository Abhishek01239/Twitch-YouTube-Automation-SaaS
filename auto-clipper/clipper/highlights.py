"""Find hype moments in long videos using audio energy (loud reactions, explosions, shouting)."""
import subprocess
from pathlib import Path

import numpy as np

from .util import log

SR = 4000  # audio rate used for analysis; plenty for loudness


def loudness_per_second(audio: Path) -> np.ndarray:
    """Stream-decode audio and return RMS loudness in dB for each second (low memory, works for long VODs)."""
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(audio), "-ac", "1", "-ar", str(SR),
                             "-f", "s16le", "-"], stdout=subprocess.PIPE)
    values: list[float] = []
    chunk = SR * 2
    assert proc.stdout
    while True:
        buf = proc.stdout.read(chunk)
        if len(buf) < chunk:
            break
        s = np.frombuffer(buf, np.int16).astype(np.float32) / 32768.0
        values.append(20 * np.log10(np.sqrt(np.mean(s * s)) + 1e-6))
    proc.wait()
    return np.array(values, dtype=np.float32)


def pick_moments(db: np.ndarray, clip_len: int, lead_in: int, top: int, min_score: float) -> list[tuple[float, float, float]]:
    """Return up to `top` (start, end, score) windows around the loudest sustained peaks."""
    n = len(db)
    if n == 0:
        return []
    if n <= clip_len:
        return [(0.0, float(n), 0.0)]
    smooth = np.convolve(db, np.ones(3) / 3, mode="same")
    # compare each second against its local surroundings (~2 min) so quiet/loud streams both work
    win = min(121, n if n % 2 else n - 1)
    pad = win // 2
    padded = np.pad(smooth, pad, mode="edge")
    local = np.convolve(padded, np.ones(win) / win, mode="valid")[:n]
    mad = np.median(np.abs(smooth - np.median(smooth))) + 1e-3
    score = (smooth - local) / (1.4826 * mad)
    score[: min(30, n // 10)] = -np.inf  # skip stream intros
    moments = []
    work = score.copy()
    while len(moments) < top:
        i = int(np.argmax(work))
        if not np.isfinite(work[i]) or work[i] < min_score:
            break
        start = max(0, i - lead_in)
        end = min(n, start + clip_len)
        start = max(0, end - clip_len)
        moments.append((float(start), float(end), float(work[i])))
        work[max(0, start - clip_len): min(n, end + clip_len)] = -np.inf
    log(f"[highlights] {len(moments)} moments: " + ", ".join(f"{s:.0f}s(score {sc:.1f})" for s, _, sc in moments))
    return sorted(moments)
