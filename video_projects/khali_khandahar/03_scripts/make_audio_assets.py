"""Procedurally synthesizes every music bed and sound effect used in the edit.
Everything is generated from math (oscillators + filtered noise), so all audio
is original and copyright-safe. Output: 44.1 kHz stereo 16-bit WAV."""
import sys, os, wave
import numpy as np

SR = 44100
OUT = sys.argv[1]
os.makedirs(os.path.join(OUT, "music"), exist_ok=True)
os.makedirs(os.path.join(OUT, "sfx"), exist_ok=True)
rng = np.random.default_rng(7)


def t_axis(sec):
    return np.arange(int(sec * SR)) / SR


def lowpass(x, cutoff):
    # one-pole low-pass, vectorised via cumulative filtering in chunks
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(0, len(x), 4096):
        seg = x[i:i + 4096]
        from scipy.signal import lfilter
        out, zf = lfilter([1 - a], [1, -a], seg, zi=[acc * a])
        y[i:i + 4096] = out
        acc = out[-1]
    return y


def bandnoise(sec, lo, hi):
    n = rng.standard_normal(int(sec * SR))
    return lowpass(n, hi) - lowpass(n, lo)


def env_adsr(n, a, d, s, r):
    e = np.ones(n) * s
    A, D, R = int(a * SR), int(d * SR), int(r * SR)
    A = max(A, 1)
    e[:A] = np.linspace(0, 1, A)
    e[A:A + D] = np.linspace(1, s, len(e[A:A + D]))
    if R:
        e[-R:] *= np.linspace(1, 0, R)
    return e


def norm(x, peak=0.89):
    m = np.max(np.abs(x)) or 1
    return x / m * peak


def stereo(l, r=None):
    if r is None:
        r = l
    return np.stack([l, r], axis=1)


def save(name, x):
    x = np.clip(x, -1, 1)
    if x.ndim == 1:
        x = stereo(x)
    data = (x * 32767).astype(np.int16)
    with wave.open(os.path.join(OUT, name), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(data.tobytes())
    print("wrote", name, f"{len(x)/SR:.1f}s")


def loop_fade(x, fade=2.0):
    """Make a buffer loop seamlessly by crossfading its tail into its head."""
    F = int(fade * SR)
    head, tail = x[:F].copy(), x[-F:].copy()
    ramp = np.linspace(0, 1, F)
    if x.ndim == 2:
        ramp = ramp[:, None]
    x = x[:-F].copy()
    x[:F] = head * ramp + tail * (1 - ramp)
    return x


# ---------------------------------------------------------------- music beds
def drone(sec, root=55.0, dark=1.0):
    t = t_axis(sec)
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * t / 13.0)
    l = (np.sin(2 * np.pi * root * t) + 0.6 * np.sin(2 * np.pi * root * 1.498 * t + 0.3)
         + 0.35 * np.sin(2 * np.pi * root * 2.003 * t) + 0.25 * np.sin(2 * np.pi * root * 1.189 * t))
    r = (np.sin(2 * np.pi * (root + 0.4) * t) + 0.6 * np.sin(2 * np.pi * root * 1.502 * t)
         + 0.35 * np.sin(2 * np.pi * root * 1.997 * t + 1) + 0.25 * np.sin(2 * np.pi * root * 1.192 * t))
    air = bandnoise(sec, 300, 1400) * (0.25 + 0.2 * lfo) * dark
    wind = bandnoise(sec, 80, 500) * (0.5 + 0.5 * np.sin(2 * np.pi * t / 7.3)) * 0.6
    l = l * (0.6 + 0.4 * lfo) + air + wind
    r = r * (0.6 + 0.4 * (1 - lfo)) + air[::-1] + wind
    return stereo(norm(l, 0.7), norm(r, 0.7))


# Dark ambient bed (indoor / exploration). 64 s seamless loop.
save("music/bed_dark_ambient_loop.wav", loop_fade(drone(66, 55.0)))

# Dusk walk bed: 84 BPM pulse + minor-key plucked arpeggio over drone.
BPM = 84
beat = 60 / BPM
bars = 16
sec = bars * 4 * beat
t = t_axis(sec)
bed = drone(sec, 49.0, 0.6) * 0.55
notes = [220.0, 261.63, 329.63, 311.13, 220.0, 261.63, 349.23, 329.63]  # A minor w/ b5 colour
pluck = np.zeros(len(t))
for i in range(int(sec / (beat / 2))):
    st = int(i * beat / 2 * SR)
    f = notes[i % len(notes)] * (0.5 if (i // 16) % 2 else 1.0)
    n = min(int(1.2 * SR), len(t) - st)
    tt = np.arange(n) / SR
    tone = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt)) * np.exp(-tt * 5)
    pluck[st:st + n] += tone * (0.9 if i % 2 == 0 else 0.55)
kick = np.zeros(len(t))
for i in range(int(sec / beat)):
    st = int(i * beat * SR)
    n = min(int(0.35 * SR), len(t) - st)
    tt = np.arange(n) / SR
    fr = 45 + 70 * np.exp(-tt * 30)
    k = np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-tt * 9)
    kick[st:st + n] += k * (1.0 if i % 2 == 0 else 0.6)  # heartbeat-like accent
pl = lowpass(pluck, 2500)
mix = bed + stereo(pl * 0.22 + kick * 0.5, np.roll(pl, 900) * 0.22 + kick * 0.5)
save("music/bed_dusk_pulse_84bpm.wav", norm(mix, 0.8))
with open(os.path.join(OUT, "music", "bed_dusk_pulse_84bpm.txt"), "w") as f:
    f.write(f"BPM={BPM}\nbeat_seconds={beat:.6f}\nbars={bars}\n")

# Climax bed: faster 112 BPM heartbeat + dissonant string-like cluster swell.
BPM2 = 112
beat2 = 60 / BPM2
sec = 32 * beat2 * 4 / 2
t = t_axis(sec)
cluster = sum(np.sin(2 * np.pi * f * t + p) for f, p in [(110, 0), (116.5, 1), (164.8, 2), (174.6, .5), (233.1, 1.3)])
cluster = lowpass(cluster + 0.15 * rng.standard_normal(len(t)), 1800) * (0.4 + 0.6 * t / sec)
hb = np.zeros(len(t))
for i in range(int(sec / beat2)):
    for off, amp in [(0, 1.0), (0.16, 0.7)]:
        st = int((i * beat2 + off) * SR)
        if st >= len(t):
            continue
        n = min(int(0.25 * SR), len(t) - st)
        tt = np.arange(n) / SR
        hb[st:st + n] += np.sin(2 * np.pi * (42 + 40 * np.exp(-tt * 25)) * tt) * np.exp(-tt * 14) * amp
mix = stereo(norm(cluster, 0.5) + hb * 0.8, norm(np.roll(cluster, 2000), 0.5) + hb * 0.8)
save("music/bed_climax_heartbeat_112bpm.wav", norm(mix, 0.85))

# ---------------------------------------------------------------- sound effects
# Riser: noise sweep + rising tone, 4 s
sec = 4.0; t = t_axis(sec)
f = 80 * (2 ** (t / sec * 4))
tone = np.sin(2 * np.pi * np.cumsum(f) / SR)
noise = rng.standard_normal(len(t))
sw = np.zeros(len(t))
for i in range(0, len(t), 2205):  # stepped LP cutoff sweep
    seg = noise[i:i + 2205]
    sw[i:i + 2205] = lowpass(seg, 200 + 8000 * (i / len(t)) ** 2)
riser = (tone * 0.5 + sw * 0.8) * (t / sec) ** 2
save("sfx/riser_4s.wav", norm(riser))

# Impact / braam: sub drop + noise burst + low brass-ish saw stack
sec = 3.5; t = t_axis(sec)
sub = np.sin(2 * np.pi * np.cumsum(30 + 90 * np.exp(-t * 6)) / SR) * np.exp(-t * 1.2)
burst = lowpass(rng.standard_normal(len(t)), 3000) * np.exp(-t * 9)
saw = sum(((t * f) % 1 * 2 - 1) for f in (55, 55.4, 82.4, 110.3)) / 4
saw = lowpass(saw, 600) * np.exp(-t * 1.0) * (1 - np.exp(-t * 40))
save("sfx/impact_braam.wav", norm(sub * 1.0 + burst * 0.5 + saw * 0.6))

# Whoosh (for transitions), 1.2 s
sec = 1.2; t = t_axis(sec)
e = np.sin(np.pi * t / sec) ** 3
w = bandnoise(sec, 300, 3500) * e
pan = t / sec
save("sfx/whoosh.wav", stereo(norm(w * (1 - pan) + 1e-9), norm(w * pan + 1e-9)) * 0.85)

# Sub hit (short boom on scare cuts)
sec = 1.6; t = t_axis(sec)
save("sfx/sub_hit.wav", norm(np.sin(2 * np.pi * np.cumsum(28 + 70 * np.exp(-t * 18)) / SR) * np.exp(-t * 3)))

# Static / glitch burst 0.6 s
sec = 0.6; t = t_axis(sec)
g = rng.standard_normal(len(t)) * (rng.random(len(t) // 400 + 1).repeat(400)[:len(t)] > 0.4)
g = g * np.sin(np.pi * t / sec) ** 0.5
save("sfx/static_glitch.wav", norm(lowpass(g, 6000)) * 0.8)

# Single heartbeat (lub-dub) 1 s
sec = 1.0; t = t_axis(sec); hb = np.zeros(len(t))
for off, amp in [(0.0, 1.0), (0.18, 0.7)]:
    st = int(off * SR); tt = t[: len(t) - st]
    hb[st:] += np.sin(2 * np.pi * (40 + 45 * np.exp(-tt * 25)) * tt) * np.exp(-tt * 13) * amp
save("sfx/heartbeat.wav", norm(hb))

# Reverse swell into a cut (reverse of a decaying chord), 2.5 s
sec = 2.5; t = t_axis(sec)
ch = sum(np.sin(2 * np.pi * f * t) for f in (146.8, 155.6, 220, 311.1)) * np.exp(-t * 2)
ch = lowpass(ch + 0.2 * rng.standard_normal(len(t)) * np.exp(-t * 3), 2500)
save("sfx/reverse_swell.wav", norm(ch[::-1]))
print("done")
