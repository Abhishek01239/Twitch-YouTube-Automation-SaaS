"""Word-by-word pop-up captions with faster-whisper, written as an ASS subtitle file."""
from pathlib import Path

from .util import log

_model = None


def _get_model(name: str):
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        log(f"[captions] loading whisper model '{name}'")
        _model = WhisperModel(name, device="cpu", compute_type="int8")
    return _model


def transcribe_words(media: Path, model_name: str, language: str | None) -> list[tuple[float, float, str]]:
    import subprocess
    import numpy as np
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(media), "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], check=True, capture_output=True).stdout
    audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
    if audio.size == 0:
        return []
    model = _get_model(model_name)
    segments, info = model.transcribe(audio, word_timestamps=True, vad_filter=True,
                                      language=None if language in (None, "", "auto") else language)
    words = [(w.start, w.end, w.word.strip()) for seg in segments for w in (seg.words or []) if w.word.strip()]
    log(f"[captions] {len(words)} words (language {info.language})")
    return words


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").upper()


HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pop,DejaVu Sans,92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,520,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

HIGHLIGHT = "&H0000F0FF&"  # yellow (ASS uses BGR)


def write_ass(words: list[tuple[float, float, str]], path: Path, max_words: int = 3, max_span: float = 1.6) -> None:
    """Group words into short phrases; each word pops in and is highlighted while spoken."""
    groups: list[list[tuple[float, float, str]]] = []
    for w in words:
        if groups and len(groups[-1]) < max_words and w[1] - groups[-1][0][0] <= max_span \
                and w[0] - groups[-1][-1][1] < 0.6:
            groups[-1].append(w)
        else:
            groups.append([w])
    lines = []
    for gi, g in enumerate(groups):
        group_end = g[-1][1]
        if gi + 1 < len(groups):
            group_end = min(group_end + 0.3, groups[gi + 1][0][0])
        for i, (start, end, _) in enumerate(g):
            seg_end = g[i + 1][0] if i + 1 < len(g) else group_end
            parts = []
            for j, (_, _, word) in enumerate(g[: i + 1]):
                if j == i:
                    parts.append("{\\c" + HIGHLIGHT + "\\fscx70\\fscy70\\t(0,90,\\fscx100\\fscy100)}" + _esc(word) + "{\\c&H00FFFFFF&}")
                else:
                    parts.append(_esc(word))
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(max(seg_end, start + 0.08))},Pop,,0,0,0,,{' '.join(parts)}")
    path.write_text(HEADER + "\n".join(lines) + "\n", encoding="utf-8")
