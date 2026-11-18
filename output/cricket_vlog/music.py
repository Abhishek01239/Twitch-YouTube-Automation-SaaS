#!/usr/bin/env python3
"""Original instrumental score for the cricket vlog, synthesised from scratch (no samples,
no third-party audio), so it is free to use.

Usage: python3 music.py <markers.json> <out.wav>
markers.json: {"end": s, "drop": s, "full": s, "stop": s, "outro": s, "duck": [[a,b],...]}
  drop  = drums/bass enter (aligned to bar 8)      full = lead melody + 16th hats
  stop  = full band cuts out (stump-hit moment)    outro = soft pads/pluck resume
"""
import json, sys, wave
import numpy as np

SR = 48000
rng = np.random.default_rng(7)
M = json.load(open(sys.argv[1]))
END, DROP, FULL, STOP, OUTRO = M["end"], M["drop"], M["full"], M["stop"], M["outro"]
BAR = DROP / 8.0                      # 8 bars of intro land exactly on the drop
BEAT = BAR / 4
N = int((END + 4) * SR)               # extra tail for reverb

def mtof(m): return 440.0 * 2 ** ((m - 69) / 12)
def t_(d): return np.arange(int(d * SR)) / SR
L = np.zeros(N); R = np.zeros(N)

def add(sig, at, pan=0.0, gain=1.0):
    i = int(at * SR)
    if i >= N or i + len(sig) <= 0: return
    if i < 0: sig, i = sig[-i:], 0
    sig = sig[: N - i] * gain
    L[i:i + len(sig)] += sig * np.sqrt(0.5 * (1 - pan))
    R[i:i + len(sig)] += sig * np.sqrt(0.5 * (1 + pan))

def fft_filter(x, lo=0.0, hi=None, slope=0.15):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR); g = np.ones_like(f)
    if hi: g *= 1 / (1 + (f / hi) ** (1 / slope * 0.5))
    if lo: g *= 1 / (1 + (lo / np.maximum(f, 1)) ** (1 / slope * 0.5))
    return np.fft.irfft(X * g, len(x))

def adsr(n, a, d, s, r, sustain_len):
    a, d, r = int(a * SR), int(d * SR), int(r * SR); sl = max(int(sustain_len * SR) - a - d, 0)
    e = np.concatenate([np.linspace(0, 1, a, endpoint=False), np.linspace(1, s, d, endpoint=False),
                        np.full(sl, s), np.linspace(s, 0, r)])
    return np.pad(e, (0, max(0, n - len(e))))[:n]

def saw(freq, dur, detune_cents=(-7, 0, 7)):
    t = t_(dur); out = np.zeros_like(t)
    for c in detune_cents:
        ph = (freq * 2 ** (c / 1200) * t + rng.random()) % 1.0
        out += 2 * ph - 1
    return out / len(detune_cents)

def pluck(freq, dur, bright=0.5, decay=0.996):
    """Karplus-Strong, vectorised per delay-line period."""
    n = int(dur * SR); P = max(2, int(SR / freq))
    buf = fft_filter(rng.uniform(-1, 1, P * 4), hi=2000 + 6000 * bright)[:P]
    out = np.zeros(n + P + 1); out[:P] = buf
    for s in range(P, n + 1, P):
        prev = out[s - P:s + 1]
        e = min(s + P, n + P + 1)
        out[s:e] = decay * 0.5 * (prev[: e - s] + prev[1: e - s + 1])
    sig = out[:n]
    return sig * np.exp(-t_(dur)[:n] * 1.2)

# D major: I - V - vi - IV  (D, A, Bm, G) — warm, slightly nostalgic
CHORDS = [  # pad voicing, bass root, arpeggio tones
    ([62, 66, 69, 74], 38, [74, 78, 81, 78, 86, 81, 78, 81]),
    ([61, 64, 69, 73], 33, [73, 76, 81, 76, 85, 81, 76, 81]),
    ([62, 66, 71, 74], 35, [74, 78, 83, 78, 86, 83, 78, 83]),
    ([62, 67, 71, 74], 31, [74, 79, 83, 79, 86, 83, 79, 83]),
]
LEAD = [  # (beat offset within 2-bar phrase, midi, beats) — simple singable motif
    [(0, 78, 1.5), (1.5, 76, 0.5), (2, 74, 1), (3, 76, 1), (4, 73, 2), (6, 76, 1), (7, 78, 1)],
    [(0, 78, 1.5), (1.5, 81, 0.5), (2, 79, 1), (3, 78, 1), (4, 74, 3), (7, 76, 1)],
]

def section_gain(t):
    """Overall level of the 'band' parts: off after STOP until OUTRO."""
    return 0.0 if STOP <= t < OUTRO else 1.0

nbars = int(np.ceil(END / BAR)) + 1
for b in range(nbars):
    t0 = b * BAR
    if t0 >= END: break
    pad, root, arp = CHORDS[b % 4]
    in_outro = t0 >= OUTRO - BAR * 0.01
    # ---- PAD (always; brighter during the action) ----
    cutoff = 900 if t0 < DROP else (1600 if t0 < FULL else 2200)
    if t0 >= STOP: cutoff = 1000
    for k, m in enumerate(pad):
        s = saw(mtof(m), BAR + 1.2) * adsr(int((BAR + 1.2) * SR), 0.35, 0.3, 0.8, 1.0, BAR)
        s = fft_filter(s, hi=cutoff)
        g = 0.05 if t0 < DROP else 0.045
        if STOP <= t0 < OUTRO: g = 0
        add(s, t0, pan=(-0.5 + k / 3), gain=g)
    # ---- PLUCK ARPEGGIO (from bar 4) ----
    if t0 >= BAR * 4 - 0.01:
        for i, m in enumerate(arp):
            ts = t0 + i * BEAT / 2
            if STOP <= ts < OUTRO or ts >= END - 0.3: continue
            g = 0.16 if t0 < DROP else 0.2
            if ts >= OUTRO: g = 0.12
            add(pluck(mtof(m), 1.4, bright=0.35 if ts < DROP else 0.55), ts,
                pan=0.35 if i % 2 else -0.35, gain=g)
    # ---- SOFT SUB in the second half of the intro ----
    if BAR * 4 <= t0 < DROP or (t0 >= OUTRO):
        s = np.sin(2 * np.pi * mtof(root + 12) * t_(BAR)) * adsr(int(BAR * SR), 0.2, 0.2, 0.7, 0.4, BAR - 0.4)
        add(s, t0, gain=0.10 if t0 < DROP else 0.07)
    if DROP - 0.01 <= t0 < STOP:
        # ---- DRUMS + BASS (the build) ----
        for beat in range(4):
            tb = t0 + beat * BEAT
            if tb >= STOP: break
            # kick on every beat in FULL, on 1 & 3 (+ "and of 3") before
            if t0 >= FULL or beat in (0, 2):
                kt = t_(0.45); f = 45 + 95 * np.exp(-kt * 28)
                k = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-kt * 7.5)
                k[:120] += rng.uniform(-0.4, 0.4, 120) * np.linspace(1, 0, 120)
                add(np.tanh(k * 1.6), tb, gain=0.55)
            if beat in (1, 3):  # clap
                c = np.zeros(int(0.35 * SR))
                for off in (0, 0.011, 0.022):
                    j = int(off * SR); seg = rng.uniform(-1, 1, len(c) - j) * np.exp(-np.arange(len(c) - j) / SR * 30)
                    c[j:] += seg[: len(c) - j]
                add(fft_filter(c, lo=900, hi=4500), tb, gain=0.22)
            # hats: 8ths, 16ths in FULL
            div = 4 if t0 >= FULL else 2
            for h in range(div):
                th = tb + h * BEAT / div
                if th >= STOP: break
                hd = 0.05 if h % 2 == 0 else 0.03
                hs = fft_filter(rng.uniform(-1, 1, int(0.12 * SR)), lo=7000) * np.exp(-t_(0.12) / hd)
                add(hs, th, pan=0.25, gain=0.07 if h % 2 == 0 else 0.045)
        # bass: root on 1, octave pops, syncopated
        for (bo, oct_, dur) in [(0, 0, 0.75), (0.75, 0, 0.25), (1.5, 12, 0.4), (2, 0, 0.75), (3, 0, 0.4), (3.5, 12, 0.4)]:
            tb = t0 + bo * BEAT
            if tb >= STOP: continue
            d = dur * BEAT; tt = t_(d + 0.08)
            s = np.sin(2 * np.pi * mtof(root + oct_) * tt) + 0.3 * np.sin(4 * np.pi * mtof(root + oct_) * tt)
            s = np.tanh(1.8 * s) * adsr(len(tt), 0.005, 0.1, 0.7, 0.08, d)
            add(s, tb, gain=0.22)
    # ---- LEAD (FULL section) ----
    if FULL - 0.01 <= t0 < STOP and (b - int(round(FULL / BAR))) % 2 == 0:
        phrase = LEAD[((b - int(round(FULL / BAR))) // 2) % 2]
        for (bo, m, nb) in phrase:
            tl = t0 + bo * BEAT; d = nb * BEAT
            if tl >= STOP: continue
            d = min(d, STOP - tl)
            tt = t_(d + 0.3); vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * tt) * np.clip(tt / 0.4, 0, 1)
            ph = np.cumsum(mtof(m) * vib) / SR
            s = 0.6 * np.sin(2 * np.pi * ph) + 0.25 * np.sin(4 * np.pi * ph) + 0.12 * np.sin(6 * np.pi * ph)
            s *= adsr(len(tt), 0.02, 0.15, 0.6, 0.3, d)
            add(s, tl, pan=0.1, gain=0.10)

# riser into the drop (noise swell over the last bar of the intro)
rd = BAR; r = fft_filter(rng.uniform(-1, 1, int(rd * SR)), lo=1500, hi=9000) * np.linspace(0, 1, int(rd * SR)) ** 2.5
add(r, DROP - rd, gain=0.12)
# soft cymbal swell on the drop
cs = fft_filter(rng.uniform(-1, 1, int(2.5 * SR)), lo=5000) * np.exp(-t_(2.5) * 1.8)
add(cs, DROP, gain=0.08); add(cs, FULL, gain=0.07)
# final ringing D chord at the end
for k, m in enumerate([50, 57, 62, 66, 69, 74]):
    add(pluck(mtof(m), 4.0, bright=0.4, decay=0.998), END - 3.4 + k * 0.03, pan=-0.4 + k * 0.16, gain=0.14)

# kick side-chain pump on pads/everything (subtle), only while drums play
env = np.ones(N)
kt = np.arange(DROP, STOP, BEAT)
for k in kt:
    i = int(k * SR); n = int(BEAT * SR * 0.9)
    env[i:i + n] = np.minimum(env[i:i + n], 1 - 0.25 * np.exp(-np.arange(n) / SR * 9)[: len(env[i:i + n])])
# duck under spoken / important natural-sound moments
for a, b in M.get("duck", []):
    i, j = int(a * SR), int(b * SR); ramp = int(0.25 * SR)
    g = np.ones(N); g[i:j] = 0.45
    g[max(i - ramp, 0):i] = np.linspace(1, 0.45, i - max(i - ramp, 0)); g[j:j + ramp] = np.linspace(0.45, 1, len(g[j:j + ramp]))
    env *= g
L *= env; R *= env
# hard stop of the dry band at the stump hit (reverb below leaves a natural tail),
# soft re-entry for the outro
gate = np.ones(N); i0, i1 = int(STOP * SR), int(OUTRO * SR); f = int(0.03 * SR)
gate[i0:i1] = 0; gate[i0 - f:i0] = np.linspace(1, 0, f)
gate[i1:i1 + int(0.6 * SR)] = np.linspace(0, 1, int(0.6 * SR))
L *= gate; R *= gate

# simple stereo reverb: convolve with exponentially decaying noise IR
ir_len = int(2.2 * SR); ir_t = np.arange(ir_len) / SR
def rev(x, seed):
    ir = np.random.default_rng(seed).uniform(-1, 1, ir_len) * np.exp(-ir_t * 3.2)
    ir = fft_filter(ir, hi=6000); n = len(x) + ir_len
    return np.fft.irfft(np.fft.rfft(x, n) * np.fft.rfft(ir, n), n)[: len(x)] * 0.012
L, R = L + rev(L, 1), R + rev(R, 2)
mix = np.stack([L, R], 1)[: int(END * SR)]
fade = int(0.02 * SR); mix[:fade] *= np.linspace(0, 1, fade)[:, None]
mix /= np.max(np.abs(mix)) / 0.89
with wave.open(sys.argv[2], "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((mix * 32767).astype(np.int16).tobytes())
print(f"music: {END:.2f}s  bar={BAR:.3f}s ({240 / BAR:.1f} BPM)")
