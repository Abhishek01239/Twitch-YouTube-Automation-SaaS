"""Audio renderer: original audio conformed to the edit + original synthesized music + SFX.

Everything musical here is generated from scratch with numpy (no samples, no third-party
recordings) so the soundtrack is copyright-safe by construction.
Usage: make_audio.py OUT.wav   (also writes stems to work/)
"""
import os
import subprocess
import sys

import numpy as np
from scipy import signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from timeline import ROOT, SEGMENTS, SRC, T, TOTAL

SR = 48000
N = int(TOTAL * SR)
BEAT = 0.5
rng = np.random.default_rng(11)


def db(x):
    return 10 ** (x / 20)


def filt(x, kind, fc, order=2):
    sos = signal.butter(order, fc, kind, fs=SR, output="sos")
    return signal.sosfilt(sos, x, axis=0)


def env_exp(n, tau):
    return np.exp(-np.arange(n) / (tau * SR))


def add(buf, x, t, gain=1.0, pan=0.0):
    i = int(round(t * SR))
    if i >= len(buf) or i < 0:
        return
    x = x[: len(buf) - i]
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    if x.ndim == 1:
        buf[i:i + len(x), 0] += x * gain * l * 1.414
        buf[i:i + len(x), 1] += x * gain * r * 1.414
    else:
        buf[i:i + len(x)] += x * gain


# ------------------------------------------------------------------ original audio, conformed
def original_track():
    out = np.zeros((N, 2), np.float32)
    for s in SEGMENTS:
        g = s.get("audio", 1.0)
        if g == 0:
            continue
        a, b = s["src"]
        sp = s["speed"]
        af = f"atempo={sp}" if sp != 1 else "anull"
        if sp < 1:  # slow motion: stretched, darker and quieter so it reads as "slow-mo"
            af += ",lowpass=f=2500"
            g *= 0.6
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.4f}", "-t", f"{b - a:.4f}", "-i", SRC, "-vn",
                              "-af", af, "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout
        x = np.frombuffer(raw, np.float32).reshape(-1, 2).copy()
        n = int(round(s["dur"] * SR))
        x = x[:n] if len(x) >= n else np.pad(x, ((0, n - len(x)), (0, 0)))
        f = min(int(0.012 * SR), n // 2)  # 12 ms fades -> click-free cuts
        ramp = np.linspace(0, 1, f)[:, None]
        x[:f] *= ramp
        x[-f:] *= ramp[::-1]
        i = int(round(s["t0"] * SR))
        out[i:i + n] += (x * g)[: N - i]
    out = filt(out, "highpass", 90)  # remove wind / handling rumble
    return out.astype(np.float32)


# ------------------------------------------------------------------ synth voices
def kick(g=1.0):
    n = int(0.42 * SR)
    t = np.arange(n) / SR
    f = 46 + 110 * np.exp(-t / 0.035)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.16)
    x += 0.35 * filt(rng.standard_normal(n), "highpass", 2500) * np.exp(-t / 0.004)
    return np.tanh(x * 1.8) * g


def clap():
    n = int(0.3 * SR)
    t = np.arange(n) / SR
    nz = filt(filt(rng.standard_normal(n), "highpass", 900), "lowpass", 6500)
    e = np.exp(-t / 0.09)
    for d in (0, 0.011, 0.023):
        e += 0.8 * np.where(t >= d, np.exp(-(t - d) / 0.006), 0)
    return nz * e * 0.5 + 0.35 * np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.05)


def hat(open_=False):
    n = int((0.22 if open_ else 0.05) * SR)
    return filt(rng.standard_normal(n), "highpass", 7500, 4) * env_exp(n, 0.07 if open_ else 0.012) * 0.3


def saw(f, n, detune=0.0):
    t = np.arange(n) / SR
    x = np.zeros(n)
    for d in (-detune, 0, detune):
        ph = (f * (1 + d) * t + rng.uniform()) % 1.0
        x += 2 * ph - 1
    return x / 3


def note(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def bass_note(m, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = 0.7 * np.sin(2 * np.pi * note(m) * t) + 0.5 * filt(saw(note(m), n), "lowpass", 420)
    e = np.minimum(t / 0.005, 1) * np.exp(-t / (dur * 0.9))
    return np.tanh(x * e * 1.6)


def pluck(m, dur=0.22, bright=3200):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = filt(saw(note(m), n, 0.006), "lowpass", bright)
    return x * np.minimum(t / 0.003, 1) * np.exp(-t / (dur * 0.35))


def stab(ms, dur=0.3):
    return sum(pluck(m, dur, 2600) for m in ms) / len(ms)


def riser(dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    nz = rng.standard_normal(n)
    out = np.zeros(n)
    blk = 2048
    for i in range(0, n, blk):  # swept band-pass noise
        fc = 300 * (20 ** (i / n))
        sos = signal.butter(2, [fc * 0.7, min(fc * 1.4, SR / 2 - 100)], "bandpass", fs=SR, output="sos")
        seg = nz[max(0, i - blk):i + blk]
        out[i:i + blk] = signal.sosfilt(sos, seg)[-min(blk, n - i) - 0:][:min(blk, n - i)] if i else signal.sosfilt(sos, seg)[:blk]
    tone = np.sin(2 * np.pi * np.cumsum(110 * 2 ** (2 * t / dur)) / SR) * 0.25
    return (out * 0.5 + tone) * (t / dur) ** 2


def whoosh(dur=0.5):
    n = int(dur * SR)
    t = np.arange(n) / SR
    nz = filt(filt(rng.standard_normal(n), "highpass", 500), "lowpass", 5000)
    e = np.sin(np.pi * t / dur) ** 3
    return nz * e * 0.5


def impact(big=True):
    n = int((1.6 if big else 0.9) * SR)
    t = np.arange(n) / SR
    f = 38 + 70 * np.exp(-t / 0.06)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (0.5 if big else 0.25))
    crack = filt(rng.standard_normal(n), "lowpass", 3500) * np.exp(-t / 0.05) * 0.7
    tail = filt(rng.standard_normal(n), "bandpass", [200, 1500]) * np.exp(-t / 0.4) * 0.15
    return np.tanh((sub + crack + tail) * 1.5)


def bat_crack():
    n = int(0.18 * SR)
    t = np.arange(n) / SR
    x = filt(rng.standard_normal(n), "bandpass", [700, 4500]) * np.exp(-t / 0.012)
    x += 0.6 * np.sin(2 * np.pi * 260 * t) * np.exp(-t / 0.03)
    return x


def alarm():
    """Two short umpire-buzzer style beeps for the No Ball call."""
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    b = (np.sign(np.sin(2 * np.pi * 620 * t)) * 0.5 + np.sin(2 * np.pi * 930 * t) * 0.5)
    b = filt(b, "lowpass", 3000) * np.minimum(t / 0.005, 1) * np.minimum((t[-1] - t) / 0.01, 1)
    out = np.zeros(int(0.6 * SR))
    out[:n] += b
    out[int(0.3 * SR):int(0.3 * SR) + n] += b
    return out * 0.5


def womp():
    """Descending 'sad trombone'-ish slide for the dot ball."""
    n = int(0.9 * SR)
    t = np.arange(n) / SR
    f = 220 * 2 ** (-8 * (t / 0.9) / 12)
    x = filt(2 * ((np.cumsum(f) / SR) % 1) - 1, "lowpass", 1400)
    vib = 1 + 0.02 * np.sin(2 * np.pi * 6 * t)
    return x * vib * np.minimum(t / 0.03, 1) * np.minimum((0.9 - t) / 0.15, 1) * 0.6


def tape_stop(x):
    """Pitch-dive the last bit of music before the No Ball call."""
    n = len(x)
    pos = np.cumsum(np.linspace(1, 0.05, n))
    pos = pos[pos < n - 1]
    i = pos.astype(int)
    fr = (pos - i)[:, None]
    y = x[i] * (1 - fr) + x[i + 1] * fr
    return y * np.linspace(1, 0, len(y))[:, None]


# ------------------------------------------------------------------ music arrangement
# A minor: Am - F - C - G, one bar (4 beats = 2 s) each
PROG = [(45, [57, 60, 64]), (41, [57, 60, 65]), (48, [55, 60, 64]), (43, [55, 59, 62])]
ARP = [0, 1, 2, 1, 0, 2, 1, 2]


def music_track():
    drums = np.zeros((N, 2))
    bass = np.zeros((N, 2))
    synth = np.zeros((N, 2))
    K, C, HH, OH = kick(), clap(), hat(), hat(True)
    nb, dot, six, six_drop = T("nb_reaction"), T("dot_result"), T("six_hit_slo"), T("six_flight")
    arms, end = T("arms_up_slo"), T("end_bg")

    def section(t):
        """Arrangement map: which layers play at time t."""
        if t < 4:
            return "intro"
        if t < 8:
            return "title"
        if t < T("pitch_walker"):
            return "full"
        if t < T("nb_delivery"):
            return "sparse"
        if t < nb:
            return "full"
        if t < T("dot_setup"):
            return "silent"
        if t < T("dot_swing_slo"):
            return "full"
        if t < dot:
            return "break"
        if t < T("dot_react"):
            return "silent"
        if t < T("six_setup"):
            return "sparse"
        if t < six:
            return "build"
        if t < six_drop:
            return "break"
        if t < T("debate_1"):
            return "peak"
        if t < arms:
            return "bed"
        if t < end:
            return "half"
        return "outro"

    nbeats = int(TOTAL / BEAT)
    for bi in range(nbeats):
        t = bi * BEAT
        sec = section(t)
        root, chord = PROG[(bi // 4) % 4]
        b4 = bi % 4
        # --- drums
        if sec in ("full", "peak"):
            add(drums, K, t, 0.9)
            if b4 in (1, 3):
                add(drums, C, t, 0.55)
            for k in range(4 if sec == "peak" else 2):
                add(drums, HH, t + k * BEAT / (4 if sec == "peak" else 2), 0.5 if k % 2 == 0 else 0.3, pan=0.25)
            add(drums, OH, t + BEAT / 2, 0.35, pan=-0.25)
        elif sec == "bed":
            add(drums, K, t, 0.7)
            if b4 in (1, 3):
                add(drums, C, t, 0.4)
            add(drums, HH, t + BEAT / 2, 0.35, pan=0.25)
        elif sec in ("title", "half"):
            if b4 == 0:
                add(drums, K, t, 1.0)
            if b4 == 2:
                add(drums, C, t, 0.7)
            add(drums, HH, t, 0.3, pan=0.25)
            add(drums, HH, t + BEAT / 2, 0.2, pan=0.25)
        elif sec == "build":
            reps = 2 if t < T("six_setup") + 1 else 4
            for k in range(reps):
                add(drums, C, t + k * BEAT / reps, 0.25 + 0.3 * (t - T("six_setup")) / 2)
            add(drums, K, t, 0.8)
        elif sec == "sparse":
            add(drums, HH, t, 0.35, pan=0.25)
            add(drums, HH, t + BEAT / 2, 0.2, pan=0.25)
            if b4 in (1, 3):
                add(drums, C, t, 0.25)
        # --- bass
        if sec in ("full", "peak", "bed", "build"):
            add(bass, bass_note(root - 12, 0.24), t, 0.55)
            add(bass, bass_note(root - 12 if b4 != 3 else root - 5, 0.22), t + BEAT / 2, 0.5)
        elif sec in ("title", "half", "intro"):
            if b4 == 0:
                add(bass, bass_note(root - 12, 1.8), t, 0.6)
        elif sec == "sparse":
            if b4 in (0, 2):
                add(bass, bass_note(root - 12, 0.2), t, 0.5)
            if b4 == 3:
                add(bass, bass_note(root - 5, 0.15), t + BEAT / 2, 0.45)
        # --- synths
        if sec in ("full", "peak", "bed"):
            add(synth, stab(chord), t + BEAT / 2, 0.5, pan=-0.3)  # off-beat stabs
            if b4 == 0:
                add(synth, stab(chord, 0.5), t, 0.45, pan=0.3)
        if sec in ("peak", "full") and (sec == "peak" or (bi // 8) % 2 == 1):
            for k in range(4):  # 16th-note arpeggio lead
                m = chord[ARP[(b4 * 4 + k) % 8] % 3] + 12
                add(synth, pluck(m, 0.16, 5200), t + k * BEAT / 4, 0.28 if sec == "peak" else 0.2, pan=0.4 * (-1) ** k)
        if sec in ("title", "half", "outro") and b4 == 0:
            ch = sum(pluck(m, 1.9, 2200) for m in chord + [chord[0] + 12]) / 4
            add(synth, ch, t, 0.9)
        if sec == "sparse":  # playful pizzicato line for the funny beats
            m = chord[[0, 2, 1, 2][b4]] + 12
            add(synth, pluck(m, 0.14, 1800), t, 0.4, pan=0.2)
            if b4 % 2 == 1:
                add(synth, pluck(m + 7, 0.1, 1800), t + BEAT / 2, 0.3, pan=-0.2)

    # side-chain style pump on bass + synths
    tt = np.arange(N) / SR
    pump = 0.45 + 0.55 * np.clip(((tt % BEAT) / BEAT) * 2.2, 0, 1)
    pumped = np.array([section(b * BEAT) in ("full", "peak", "bed", "build") for b in range(nbeats + 1)])
    pump = np.where(pumped[np.minimum((tt / BEAT).astype(int), nbeats)], pump, 1.0)[:, None]
    mix = drums * 0.9 + (bass * 0.8 + filt(synth, "highpass", 180) * 0.75) * pump

    # tape-stop into the No Ball call
    i0, i1 = int((nb - 0.5) * SR), int(nb * SR)
    ts = tape_stop(mix[i0:i1].copy())
    mix[i0:i1] = 0
    mix[i0:i0 + len(ts)] = ts
    # cinematic low drone under the intro + the silent comedy beats
    for (a, b, g) in [(0, 4, 0.3), (nb, T("dot_setup"), 0.22), (six, six_drop, 0.3)]:
        n = int((b - a) * SR)
        t = np.arange(n) / SR
        d = (np.sin(2 * np.pi * 55 * t) + 0.5 * np.sin(2 * np.pi * 82.4 * t) + 0.3 * np.sin(2 * np.pi * 110.3 * t))
        d *= np.minimum(t / 0.3, 1) * np.minimum((t[-1] - t) / 0.3, 1) * (1 + 0.2 * np.sin(2 * np.pi * 0.7 * t))
        add(mix, d, a, g)
    # outro fade
    fo = int(2.2 * SR)
    mix[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.5
    return mix


def sfx_track():
    s = np.zeros((N, 2))
    big, small, wh, bc = impact(True), impact(False), whoosh(0.5), bat_crack()
    # impacts on the hits / title slams (all on the beat)
    for name, g in [("hook_six_slo", 1.0), ("b1_hit_slo", 0.8), ("b2_hit_slo", 0.8), ("nb_reaction", 0.9),
                    ("six_hit_slo", 1.0), ("six_flight", 0.9), ("end_bg", 0.9)]:
        add(s, big, T(name), g)
    for t in (4.0, 4.5):
        add(s, small, t, 0.7)
    add(s, big, 5.0, 1.0)  # "VS" slam
    for t, g in [(1.5, .6), (2.0, .6), (2.5, .7), (T("b1_four"), .6), (T("b2_four"), .6), (T("dot_result"), .5),
                 (T("arms_up_slo"), .7), (57.5, .5), (58.0, .5)]:
        add(s, small, t, g)
    # synthetic bat 'crack' sweetener layered on the real contact
    for name in ("hook_six_slo", "b1_hit_slo", "b2_hit_slo", "six_hit_slo"):
        add(s, bc, T(name), 0.8)
    # whooshes on transitions (peak lands on the cut)
    for t, p in [(4.0, -0.5), (8.0, 0.5), (T("changeover_ff"), -0.6), (T("walk_in"), 0.6), (T("stance"), -0.4),
                 (T("pitch_walker"), 0.5), (T("dot_setup"), -0.5), (T("six_setup"), 0.5), (T("debate_1"), -0.4),
                 (T("end_bg"), 0.4)]:
        add(s, wh, t - 0.25, 0.8, pan=p)
    add(s, whoosh(1.0), T("changeover_ff"), 0.5)  # fast-forward rush
    # risers
    add(s, riser(1.5), 2.5, 0.5)
    add(s, riser(1.0), 7.0, 0.5)
    add(s, riser(2.0), T("six_setup"), 0.6)
    # no ball buzzer, dot-ball slide
    add(s, alarm(), T("nb_reaction") + 0.05, 0.6)
    add(s, womp(), T("dot_result") + 0.1, 0.55)
    return s


def envelope(x, win=0.05):
    e = np.sqrt(signal.fftconvolve((x ** 2).mean(axis=1), np.ones(int(win * SR)) / int(win * SR), "same").clip(0))
    return e


def main():
    out = sys.argv[1]
    orig = original_track()
    # level the original: gentle compression so quiet banter and loud shouts sit together
    e = envelope(orig, 0.08) + 1e-5
    target = np.percentile(e[e > np.percentile(e, 40)], 80)
    gain = np.clip((target / e) ** 0.55, db(-10), db(9))
    gain = signal.fftconvolve(gain, np.ones(int(0.15 * SR)) / int(0.15 * SR), "same")
    orig = orig * gain[:, None]
    orig *= db(-17) / (np.sqrt((orig ** 2).mean()) + 1e-9)

    music = music_track()
    music *= db(-17.5) / np.sqrt((music ** 2).mean())
    sfx = sfx_track()
    sfx *= db(-9) / np.abs(sfx).max()

    # duck the music under voices / natural sound
    e = envelope(orig, 0.12)
    duck = 1 - 0.62 * np.clip(e / (np.percentile(e, 85) + 1e-9), 0, 1)
    duck = signal.fftconvolve(duck, np.ones(int(0.25 * SR)) / int(0.25 * SR), "same")
    music = music * duck[:, None]

    mix = orig + music + sfx
    mix = np.tanh(mix * 1.15) / 1.15  # soft-clip safety before loudness normalisation
    for name, x in [("stem_original", orig), ("stem_music", music), ("stem_sfx", sfx), ("premix", mix)]:
        p = out if name == "premix" else os.path.join(ROOT, "work", name + ".wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a",
                        "pcm_s16le", p], input=np.clip(x, -1, 1).astype(np.float32).tobytes())
    print("audio ok", TOTAL, "s; rms dB orig/music/sfx:",
          [round(20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9), 1) for x in (orig, music, sfx)])


if __name__ == "__main__":
    main()
