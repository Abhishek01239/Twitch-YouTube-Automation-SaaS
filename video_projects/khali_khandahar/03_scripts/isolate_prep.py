"""Prepare / unpack audio for ElevenLabs Voice Isolator.

prep:   python3 isolate_prep.py prep <project>
        Concatenates the RAW source audio of every dialogue clip in the EDL (no cards, credits,
        muted or speed-ramped music shots) into 05_work/voice/isolator_in.wav (+ .mp3 for upload)
        and records each clip's offset in isolator_map.json. Only these ~9.7 min are sent, to fit
        the ElevenLabs free-tier credits.
unpack: python3 isolate_prep.py unpack <project> <isolated.(mp3|wav)>
        Splits the isolated result back and writes 05_work/voice/dialogue_isolated.wav: a
        full-length (source-timeline) track whose dialogue clips come from the isolator, blended
        with some de-noised ambience so the horror atmosphere isn't stripped completely; all
        other regions fall back to the noisereduce track.
"""
import json, os, subprocess, sys, wave
import numpy as np

mode, P = sys.argv[1], os.path.abspath(sys.argv[2])
V = os.path.join(P, "05_work", "voice")
SR = 48000
edl = json.load(open(os.path.join(P, "03_scripts", "edl.json")))
SKIP = ("disclaimer", "opening credits + title")


def sel_clips():
    return [c for c in edl["clips"] if not c.get("card") and not c.get("mute")
            and c.get("speed", 1) <= 1.25 and c["label"] not in SKIP]


def read(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768


def write(path, mono):
    y = np.clip(np.stack([mono, mono], 1), -1, 1)
    w = wave.open(path, "wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((y * 32767).astype(np.int16).tobytes()); w.close()


raw = read(os.path.join(P, edl["source"]))
if mode == "prep":
    parts, m, pos = [], [], 0
    for c in sel_clips():
        a, b = int(round(c["in"] * SR)), int(round(c["out"] * SR))
        parts.append(raw[a:b]); m.append({"label": c["label"], "src_a": a, "src_b": b, "pos": pos}); pos += b - a
    x = np.concatenate(parts)
    write(os.path.join(V, "isolator_in.wav"), x)
    json.dump(m, open(os.path.join(V, "isolator_map.json"), "w"), indent=1)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", os.path.join(V, "isolator_in.wav"), "-ac", "1",
                    "-c:a", "libmp3lame", "-b:a", "192k", os.path.join(V, "isolator_in.mp3")], check=True)
    print(f"{len(m)} clips, {pos / SR:.2f} s -> isolator_in.mp3")
else:
    iso = read(sys.argv[3])
    m = json.load(open(os.path.join(V, "isolator_map.json")))
    need = m[-1]["pos"] + (m[-1]["src_b"] - m[-1]["src_a"])
    print(f"isolated length {len(iso) / SR:.3f}s, expected {need / SR:.3f}s")
    if len(iso) < need:
        iso = np.pad(iso, (0, need - len(iso)))
    nr = read(os.path.join(V, "dialogue_enhanced.wav"))  # noisereduce track = fallback + ambience
    out = nr.copy()
    for e in m:
        n = e["src_b"] - e["src_a"]
        seg = iso[e["pos"]: e["pos"] + n]
        # match loudness of the isolated voice to the de-noised track, then blend in 25% ambience
        g = (np.sqrt(np.mean(nr[e["src_a"]:e["src_b"]] ** 2)) + 1e-6) / (np.sqrt(np.mean(seg ** 2)) + 1e-6)
        g = float(np.clip(g, 0.5, 4.0))
        out[e["src_a"]:e["src_b"]] = 0.85 * seg * g + 0.25 * nr[e["src_a"]:e["src_b"]]
    write(os.path.join(V, "dialogue_isolated.wav"), out)
    print("wrote dialogue_isolated.wav")
