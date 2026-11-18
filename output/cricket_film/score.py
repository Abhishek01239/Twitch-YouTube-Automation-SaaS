#!/usr/bin/env python3
"""Original score for "ONE DAY. ONE GAME." — synthesised from scratch (no samples, no
third-party audio), so it is free to use. Every section is cued to the picture.

Usage: python3 score.py <cues.json> <out.wav>
cues: hook, arrival, build, pause, hero, stop, human, ending, end (seconds)
"""
import json, sys, wave
import numpy as np

SR = 48000
C = json.load(open(sys.argv[1]))
END = C["end"]; N = int((END + 3) * SR)
rng = np.random.default_rng(11)
L = np.zeros(N); R = np.zeros(N)
BPM = 92.0; BEAT = 60 / BPM; BAR = 4 * BEAT

def mtof(m): return 440.0 * 2 ** ((m - 69) / 12)
def tt(d): return np.arange(int(d * SR)) / SR
def add(x, at, pan=0.0, g=1.0):
    i = int(at * SR)
    if i >= N or len(x) == 0: return
    if i < 0: x, i = x[-i:], 0
    x = x[: N - i] * g
    L[i:i + len(x)] += x * np.sqrt(0.5 * (1 - pan)); R[i:i + len(x)] += x * np.sqrt(0.5 * (1 + pan))
def lp(x, hi, order=2.0):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(X / (1 + (f / hi) ** (2 * order)) ** 0.5, len(x))
def hp(x, lo, order=2.0):
    X = np.fft.rfft(x); f = np.maximum(np.fft.rfftfreq(len(x), 1 / SR), 1)
    return np.fft.irfft(X / (1 + (lo / f) ** (2 * order)) ** 0.5, len(x))
def env(n, a, r, hold=None):
    a, r = max(1, int(a * SR)), max(1, int(r * SR)); h = n - a - r if hold is None else int(hold * SR)
    e = np.concatenate([np.linspace(0, 1, a), np.ones(max(h, 0)), np.linspace(1, 0, r)])
    return np.pad(e, (0, max(0, n - len(e))))[:n]

def piano(m, dur=3.0, vel=1.0):
    """Additive piano-ish tone: slightly inharmonic partials, faster decay up the series, hammer."""
    f0 = mtof(m); t = tt(dur); x = np.zeros_like(t)
    for k in range(1, 9):
        fk = f0 * k * np.sqrt(1 + 0.0004 * k * k)
        if fk > 12000: break
        x += (0.6 / k ** 1.1) * np.sin(2 * np.pi * fk * t) * np.exp(-t * (0.9 + 0.55 * k) * (1 + f0 / 1500))
    x += hp(rng.uniform(-1, 1, len(t)), 1500) * np.exp(-t * 90) * 0.08
    x *= np.minimum(1, t / 0.004)
    return np.tanh(x * 1.2 * vel) * 0.8

def strings(m, dur, att=0.9, rel=1.2, bright=1800):
    n = int((dur + rel) * SR); t = np.arange(n) / SR; x = np.zeros(n)
    for c in (-9, -3, 3, 9):
        vib = 1 + 0.0025 * np.sin(2 * np.pi * (5 + c * 0.05) * t + rng.random() * 6)
        ph = np.cumsum(mtof(m) * 2 ** (c / 1200) * vib) / SR
        x += 2 * (ph % 1) - 1
    return lp(x / 4, bright) * env(n, att, rel)

def kick():
    t = tt(0.5); f = 42 + 110 * np.exp(-t * 30)
    k = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 6)
    return np.tanh(k * 1.8)
def snare():
    t = tt(0.4); n = hp(rng.uniform(-1, 1, len(t)), 1200) * np.exp(-t * 16)
    b = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 25)
    return lp(n * 0.7 + b * 0.5, 7000)
def hat(open_=False):
    d = 0.25 if open_ else 0.07; t = tt(d)
    return hp(rng.uniform(-1, 1, len(t)), 8000) * np.exp(-t / (0.08 if open_ else 0.018))
def cymbal(d=3.0):
    t = tt(d); return hp(rng.uniform(-1, 1, len(t)), 4500) * np.exp(-t * 1.6)

# chord sets: (pad voicing, bass, arpeggio tones)
SOFT = [([59, 62, 66], 35, [71, 74, 78, 74]),   # Bm   (vi IV I V — nostalgic)
        ([55, 59, 62], 31, [67, 71, 74, 71]),   # G
        ([57, 62, 66], 38, [69, 74, 78, 74]),   # D/A
        ([57, 61, 64], 33, [69, 73, 76, 73])]   # A
LIFT = [([62, 66, 69], 38, [74, 78, 81, 78]),   # D    (I V vi IV — uplifting)
        ([61, 64, 69], 33, [73, 76, 81, 76]),   # A
        ([62, 66, 71], 35, [74, 78, 83, 78]),   # Bm
        ([62, 67, 71], 31, [74, 79, 83, 79])]   # G

def bars(t0, t1):
    b = 0
    while t0 + b * BAR < t1 - 0.05:
        yield b, t0 + b * BAR; b += 1

# ---------------- HOOK: low drone, then a single piano chord on the title freeze
d = C["arrival"] - C["hook"]
dr = (np.sin(2 * np.pi * mtof(26) * tt(d + 1)) + 0.5 * np.sin(2 * np.pi * mtof(33) * tt(d + 1)))
add(lp(dr, 300) * env(len(dr), 1.2, 1.0), C["hook"], g=0.16)
for k, m in enumerate([50, 57, 62, 66, 69]):
    add(piano(m, 4.0, 0.8), C["title"] + k * 0.025, pan=-0.3 + k * 0.15, g=0.20)

# ---------------- ARRIVAL: sparse piano + warm strings, no drums
for b, t0 in bars(C["arrival"], C["build"]):
    pad, bass, arp = SOFT[b % 4]
    for k, m in enumerate(pad): add(strings(m, BAR, 1.2, 1.4, 1300), t0, pan=-0.4 + 0.4 * k, g=0.045)
    add(piano(bass + 12, 4, 0.7), t0, g=0.18)
    for i, m in enumerate([arp[0], arp[2]]):
        add(piano(m, 3, 0.6), t0 + (i * 2 + 1) * BEAT, pan=0.3 if i else -0.3, g=0.14)

# ---------------- BUILD: 8th-note piano pulse, soft kick, swelling strings, riser to the pause
nb = sum(1 for _ in bars(C["build"], C["pause"]))
for b, t0 in bars(C["build"], C["pause"]):
    pad, bass, arp = LIFT[b % 4]; p = (b + 1) / max(nb, 1)
    for k, m in enumerate(pad): add(strings(m, BAR, 0.6, 0.8, 1300 + 1500 * p), t0, pan=-0.4 + 0.4 * k, g=0.04 + 0.03 * p)
    for i in range(8):
        ts = t0 + i * BEAT / 2
        if ts >= C["pause"] - 0.05: break
        add(piano(arp[i % 4], 1.2, 0.55 + 0.35 * p), ts, pan=0.25 if i % 2 else -0.25, g=0.12)
    for beat in (0, 2) if p < 0.5 else (0, 1, 2, 3):
        tb = t0 + beat * BEAT
        if tb < C["pause"] - 0.05: add(kick(), tb, g=0.30 + 0.15 * p)
    bs = np.sin(2 * np.pi * mtof(bass) * tt(BAR)) * env(int(BAR * SR), 0.02, 0.3)
    add(np.tanh(bs * 1.5), t0, g=0.16)
rd = min(3.0, C["pause"] - C["build"]); rz = hp(rng.uniform(-1, 1, int(rd * SR)), 2500) * np.linspace(0, 1, int(rd * SR)) ** 3
add(rz, C["pause"] - rd, g=0.10)

# ---------------- PAUSE: music drops out; just a held low tension tone
d = C["hero"] - C["pause"]
ten = np.sin(2 * np.pi * mtof(38) * tt(d)) + 0.4 * np.sin(2 * np.pi * mtof(45) * tt(d) * 1.003)
TENSION = (lp(ten, 400) * np.linspace(0.3, 1, len(ten)) * env(len(ten), 0.3, 0.05), C["pause"])

# ---------------- HERO RETURN → STOP: full band, uplifting
add(cymbal(3.5), C["hero"], g=0.16)
for b, t0 in bars(C["hero"], C["stop"]):
    pad, bass, arp = LIFT[b % 4]
    for k, m in enumerate(pad + [pad[0] + 12]):
        add(strings(m, BAR, 0.15, 0.6, 3200), t0, pan=-0.5 + 0.33 * k, g=0.045)
    for i in range(8):
        ts = t0 + i * BEAT / 2
        if ts < C["stop"]: add(piano(arp[i % 4] + (12 if i in (3, 7) else 0), 1.0, 1.0), ts, pan=0.25 if i % 2 else -0.25, g=0.12)
    for beat in range(4):
        tb = t0 + beat * BEAT
        if tb >= C["stop"]: break
        add(kick(), tb, g=0.5)
        if beat in (1, 3): add(snare(), tb, g=0.26)
        for h in range(4):
            th = tb + h * BEAT / 4
            if th < C["stop"]: add(hat(h == 2), th, pan=0.3, g=0.05 if h % 2 else 0.07)
    for (bo, o, dd) in [(0, 0, 0.9), (1, 12, 0.4), (1.5, 0, 0.4), (2, 0, 0.9), (3, 12, 0.4), (3.5, 0, 0.4)]:
        tb = t0 + bo * BEAT
        if tb >= C["stop"]: continue
        s = np.sin(2 * np.pi * mtof(bass + o) * tt(dd * BEAT + 0.05))
        add(np.tanh(2 * s) * env(len(s), 0.004, 0.05), tb, g=0.20)
    # lead melody, long notes over the top
    mel = [78, 76, 74, 73] if b % 2 == 0 else [74, 76, 78, 81]
    for i, m in enumerate(mel[:2]):
        tl = t0 + i * 2 * BEAT
        if tl >= C["stop"]: continue
        dd = min(2 * BEAT, C["stop"] - tl)
        add(strings(m + 12, dd, 0.08, 0.4, 5000), tl, pan=0.1, g=0.035)

# ---------------- HUMAN + ENDING: soft piano and strings, resolving to D
for b, t0 in bars(C["human"], C["end"] - 2.6):
    pad, bass, arp = SOFT[b % 4] if t0 < C["ending"] else LIFT[(b % 2) * 3]
    for k, m in enumerate(pad): add(strings(m, BAR, 1.0, 1.5, 1100), t0, pan=-0.4 + 0.4 * k, g=0.04)
    add(piano(bass + 12, 4, 0.6), t0, g=0.14)
    add(piano(arp[1], 3, 0.5), t0 + 2 * BEAT, pan=0.3, g=0.11)
for k, m in enumerate([38, 50, 57, 62, 66, 69, 74]):
    add(piano(m, 5.0, 0.7), C["end"] - 2.9 + k * 0.04, pan=-0.45 + k * 0.15, g=0.17)
add(strings(62, 2.0, 1.0, 2.0, 1000), C["end"] - 3.4, g=0.05)

# hard cut of the band at the stump hit (reverb gives the natural tail), soft re-entry
gate = np.ones(N); i0, i1 = int(C["stop"] * SR), int(C["human"] * SR); f = int(0.02 * SR)
gate[i0:i1] = 0; gate[i0 - f:i0] = np.linspace(1, 0, f); gate[i1:i1 + SR] = np.linspace(0, 1, SR)
# the held breath before the hero shot: build cuts clean, only the tension tone remains
p0, p1, pf = int(C["pause"] * SR), int(C["hero"] * SR), int(0.12 * SR)
dry_tension = np.zeros(N)
gate[p0:p1] = 0; gate[p0 - pf:p0] = np.linspace(1, 0, pf)
L *= gate; R *= gate
add(TENSION[0], TENSION[1], g=0.07)

# stereo room reverb
irl = int(2.6 * SR); it = np.arange(irl) / SR
def rev(x, seed):
    ir = lp(np.random.default_rng(seed).uniform(-1, 1, irl), 5000) * np.exp(-it * 2.6)
    n = len(x) + irl; return np.fft.irfft(np.fft.rfft(x, n) * np.fft.rfft(ir, n), n)[: len(x)] * 0.010
L, R = L + rev(L, 3), R + rev(R, 4)
mix = np.stack([L, R], 1)[: int(END * SR)]
mix /= np.max(np.abs(mix)) / 0.89
with wave.open(sys.argv[2], "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((mix * 32767).astype(np.int16).tobytes())
print(f"score {END:.2f}s @ {BPM} BPM")
