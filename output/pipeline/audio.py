"""Original procedurally-synthesised drift-phonk score + SFX (100% copyright-safe)."""
import numpy as np, wave, sys
from scipy.signal import butter, sosfilt, fftconvolve
from timeline import *

SR = 48000
N = int(DURATION * SR) + SR  # 1s tail buffer
rng = np.random.default_rng(7)

def t_(d): return np.arange(int(d * SR)) / SR
def bp(x, lo, hi, o=4): return sosfilt(butter(o, [lo, hi], 'band', fs=SR, output='sos'), x)
def lp(x, f, o=4): return sosfilt(butter(o, f, 'low', fs=SR, output='sos'), x)
def hp(x, f, o=4): return sosfilt(butter(o, f, 'high', fs=SR, output='sos'), x)
def env(d, a=0.002, dec=0.2):
    t = t_(d); e = np.exp(-t / dec); na = max(1, int(a * SR)); e[:na] *= np.linspace(0, 1, na); return e

class Bus:
    def __init__(s): s.L = np.zeros(N); s.R = np.zeros(N)
    def add(s, x, at, g=1.0, pan=0.0):
        i = int(at * SR)
        if i >= N: return
        x = x[:N - i]
        s.L[i:i + len(x)] += x * g * np.sqrt(0.5 * (1 - pan))
        s.R[i:i + len(x)] += x * g * np.sqrt(0.5 * (1 + pan))
    def addst(s, l, r, at, g=1.0):
        i = int(at * SR); l = l[:N - i]; r = r[:N - i]
        s.L[i:i + len(l)] += l * g; s.R[i:i + len(r)] += r * g

def reverb(x, sec=1.8, mix=0.3, seed=1):
    r = np.random.default_rng(seed)
    n = int(sec * SR); t = np.arange(n) / SR
    ir = r.standard_normal(n) * np.exp(-t * 6.9 / sec)
    ir = lp(ir, 6000); ir /= np.sqrt((ir ** 2).sum())
    wet = fftconvolve(x, ir)[:len(x)]
    return x * (1 - mix) + wet * mix * 0.6

# ---------------- instruments ----------------
def kick():
    d = 0.45; t = t_(d)
    f = 45 + 160 * np.exp(-t / 0.03)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * env(d, 0.001, 0.16)
    click = hp(rng.standard_normal(len(t)), 3000) * env(d, 0.0005, 0.004) * 0.4
    return np.tanh(1.8 * (x + click))

def b808(freq, d):
    t = t_(d)
    f = freq * (1 + 1.5 * np.exp(-t / 0.015))
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * env(d, 0.003, d * 0.55)
    rel = np.ones_like(t); nr = int(0.03 * SR); rel[-nr:] = np.linspace(1, 0, nr)
    x = np.tanh(3.5 * x) * rel  # distorted phonk 808
    return lp(x, 900) * 0.9

def clap():
    d = 0.35; t = t_(d)
    n = rng.standard_normal(len(t))
    e = np.zeros_like(t)
    for o in (0, 0.010, 0.020):
        i = int(o * SR); e[i:] += np.exp(-(t[:len(t) - i]) / 0.008)
    e += np.exp(-t / 0.09) * 0.6
    return reverb(bp(n, 900, 5500) * e, 0.6, 0.25, 3) * 0.8

def hat(open_=False):
    d = 0.25 if open_ else 0.05
    n = rng.standard_normal(int(d * SR))
    return hp(n, 7500) * env(d, 0.0005, 0.08 if open_ else 0.012) * 0.35

def cowbell(semi=0, d=0.22):
    t = t_(d); k = 2 ** (semi / 12)
    sq = lambda f: np.sign(np.sin(2 * np.pi * f * k * t))
    x = (sq(540) + sq(800)) * 0.5
    x = bp(x, 450 * k, 2600 * k, 2)
    return x * env(d, 0.001, 0.07) * 0.55

def pad(freqs, d):
    t = t_(d); x = np.zeros_like(t)
    for f in freqs:
        for det in (-0.12, 0, 0.11):
            ff = f * 2 ** (det / 12)
            x += 2 * ((t * ff) % 1) - 1
    x = lp(x, 1400) / (len(freqs) * 3)
    a = np.minimum(1, t / 0.4) * np.minimum(1, (d - t) / 0.6)
    return x * a * 0.5

# ---------------- SFX ----------------
def siren(d, mode="wail"):
    t = t_(d)
    if mode == "wail":
        f = 950 + 450 * np.sin(2 * np.pi * t / 3.2 - np.pi / 2)
    else:  # yelp
        f = 950 + 450 * np.sin(2 * np.pi * t * 3.2 - np.pi / 2)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.15 * np.sin(3 * ph)
    x = np.tanh(1.5 * x)
    x = bp(x, 500, 4500, 2)
    a = np.minimum(1, t / 0.15) * np.minimum(1, (d - t) / 0.3)
    return x * a * 0.22

def engine(d, f0=45, f1=190, curve=0.6, shift=None):
    t = t_(d); u = t / d
    f = f0 + (f1 - f0) * u ** curve
    if shift:  # gear shift dip
        for s in shift:
            m = t > s; f[m] = f[m] - (f1 - f0) * 0.35 * np.exp(-(t[m] - s) / 0.25)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = sum(np.sin(k * ph + rng.uniform(0, 6)) / k ** 0.7 for k in range(1, 9))
    fire = 1 + 0.5 * np.sign(np.sin(ph * 0.5))  # cylinder firing roughness
    x = x * fire + 0.4 * lp(rng.standard_normal(len(t)), 2000) * (0.4 + u)
    x = np.tanh(1.6 * x)
    x = lp(x, 3500)
    a = np.minimum(1, t / 0.08) * np.minimum(1, (d - t) / 0.25)
    return x * a * 0.35

def flyby(d=1.6):
    t = t_(d); c = d / 2
    dist = np.sqrt(((t - c) * 60) ** 2 + 4)
    dop = 340 / (340 + 60 * (t - c) / dist * 1.0)
    f = 130 * dop
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = sum(np.sin(k * ph) / k for k in range(1, 8))
    x = np.tanh(1.5 * x) / dist * 2
    pan = np.clip((t - c) * 1.2, -1, 1)
    l = x * np.sqrt(0.5 * (1 - pan)); r = x * np.sqrt(0.5 * (1 + pan))
    return lp(l, 4000) * 0.5, lp(r, 4000) * 0.5

def screech(d):
    t = t_(d)
    n = rng.standard_normal(len(t))
    band = bp(n, 1400, 3200, 2)
    f = 2100 + 250 * np.sin(2 * np.pi * 7 * t) + 120 * rng.standard_normal(len(t)).cumsum() / np.sqrt(SR) * 0.05
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * (0.6 + 0.4 * np.sin(2 * np.pi * 13 * t))
    x = band * 0.8 + tone * 0.35
    a = np.minimum(1, t / 0.05) * np.minimum(1, (d - t) / 0.4)
    return np.tanh(1.3 * x) * a * 0.3

def impact(d=2.5):
    t = t_(d)
    f = 30 + 70 * np.exp(-t / 0.12)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(d, 0.001, 0.6)
    crack = bp(rng.standard_normal(len(t)), 200, 8000) * env(d, 0.0005, 0.05)
    return reverb(np.tanh(2 * (boom + 0.6 * crack)), 2.5, 0.35, 5) * 0.9

def whoosh(d=0.6, up=True):
    t = t_(d); n = rng.standard_normal(len(t)); out = np.zeros_like(t)
    seg = int(0.02 * SR)
    for i in range(0, len(t), seg):
        u = i / len(t); u = u if up else 1 - u
        fc = 300 + 5000 * u ** 2
        out[i:i + seg] = bp(n[max(0, i - 2000):i + seg], fc * 0.6, fc * 1.4, 2)[-len(n[i:i + seg]):]
    a = np.sin(np.pi * t / d) ** 2
    return out * a * 0.5

def riser(d):
    t = t_(d); u = t / d
    n = rng.standard_normal(len(t))
    x = bp(n, 800, 9000, 2) * u ** 2 * 0.25
    f = 200 * 2 ** (3 * u)
    x += np.sin(2 * np.pi * np.cumsum(f) / SR) * u ** 2 * 0.15
    return x

def city(d):
    n = rng.standard_normal(int(d * SR))
    rumble = lp(n, 400) * 0.8
    crowd = bp(rng.standard_normal(len(n)), 300, 2500) * (0.5 + 0.5 * np.abs(np.sin(np.arange(len(n)) / SR * 1.7))) * 0.15
    return rumble + crowd

def horn(d=0.5, f=420):
    t = t_(d)
    x = np.sign(np.sin(2 * np.pi * f * t)) + np.sign(np.sin(2 * np.pi * f * 1.26 * t))
    return lp(x, 2500) * np.minimum(1, (d - t) / 0.05) * 0.04

# ---------------- arrangement ----------------
music, sfx = Bus(), Bus()
K, C, HH = kick(), clap(), hat()
ROOTS = [41.2, 49.0, 36.7, 46.25]           # E1 G1 D1 F#1
ROOT_SEMI = [0, 3, -2, 2]
COW_PAT = [0, None, 0, 7, None, 5, 3, None, 0, None, 3, 5, None, 7, 10, 7]  # 16ths
nbars = int(DURATION / BAR) + 1

for bar in range(nbars):
    t0 = bar * BAR
    if t0 >= DURATION - 0.5: break
    sec_intro = bar < 1
    sec_club = CLUB <= t0 < CHASE
    sec_end = t0 >= ENDING
    chord = bar % 4
    root = ROOTS[chord]
    # pads everywhere (atmosphere)
    f = root * 4
    music.add(pad([f, f * 1.189, f * 1.498], BAR + 0.3), t0, 0.5 if not sec_end else 0.8)
    if sec_intro:
        continue
    endfade = 1.0
    if sec_end:
        if t0 >= ENDCARD + BAR: continue  # drums out for the final bars
        endfade = 0.55
    # kick + 808 (phonk half-time groove)
    kpat = [0, 2.5] if not sec_club else [0, 2.75]
    for kb in kpat + ([3.5] if bar % 2 else []):
        music.add(K, t0 + b(kb), 0.9 * endfade)
    music.add(b808(root, BAR * 0.62), t0, 0.8 * endfade)
    music.add(b808(root * (1.335 if chord % 2 else 1.0), BAR * 0.3), t0 + b(2.5), 0.7 * endfade)
    # clap on 3 (half-time)
    music.add(C, t0 + b(2), 0.75 * endfade)
    # hats: 8ths, with triplet/32nd rolls at bar ends (more in chase)
    step = 0.5 if sec_club else 0.25
    nb = 0
    while nb < 4:
        if (CHASE <= t0 < ENDING) and nb >= 3 and bar % 2:
            for r in range(6): music.add(HH, t0 + b(nb + r / 6), 0.6 * endfade, pan=0.3)
            nb += 1; continue
        music.add(HH, t0 + b(nb), (0.7 if nb % 1 == 0 else 0.45) * endfade, pan=0.25)
        nb += step
    if bar % 2 == 1: music.add(hat(True), t0 + b(3.5), 0.4 * endfade, pan=-0.2)
    # cowbell melody (the phonk signature)
    if not sec_club or bar % 2 == 0:
        for i, s in enumerate(COW_PAT):
            if s is None: continue
            music.add(cowbell(s + ROOT_SEMI[chord]), t0 + b(i / 4), 0.55 * endfade, pan=-0.15 if i % 2 else 0.15)

# music bus FX: reverb send + club muffle
ML = reverb(music.L, 1.5, 0.18, 11); MR = reverb(music.R, 1.5, 0.18, 12)
def muffle(x, a, bnd):
    i0, i1 = int(a * SR), int(bnd * SR)
    seg = x[i0:i1]
    m = lp(seg, 700)
    fade = np.ones(len(seg)); nf = int(0.25 * SR)
    w = np.ones(len(seg)); w[:nf] = np.linspace(0, 1, nf); w[-nf:] = np.linspace(1, 0, nf)
    x[i0:i1] = seg * (1 - w * 0.75) + m * w * 0.75 * 1.4
    return x
# first half of the club scene sounds like it's heard from inside the club walls
ML = muffle(ML, CLUB, CLUB + 2 * BAR); MR = muffle(MR, CLUB, CLUB + 2 * BAR)
# intro: low-passed teaser
ML = muffle(ML, 0, DROP); MR = muffle(MR, 0, DROP)

# ---- SFX placement ----
sfx.add(impact(), 0.0, 0.7)
sfx.add(siren(2.2, "yelp"), 0.0, 0.9, pan=-0.3)
sfx.add(engine(0.9, 60, 230, 0.5), 0.86, 0.9)
sfx.add(riser(DROP - 0.3), 0.3, 0.8)
for at in BIG_CUTS:
    sfx.add(impact(), at, 0.75)
    sfx.add(whoosh(0.5), at - 0.45, 0.8)
for (sb, eb, *_r) in SHOTS:
    if b(sb) not in BIG_CUTS and sb > 2:
        sfx.add(whoosh(0.3), b(sb) - 0.25, 0.35, pan=rng.uniform(-.5, .5))
# city ambience during aerial + ending
sfx.add(city(CAR - DROP + 0.5) * lp(np.ones(1), 1)[0], DROP, 0.25)
for at in (2.4, 3.9): sfx.add(horn(0.35, rng.uniform(380, 480)), at, 1.0, pan=rng.uniform(-.8, .8))
sfx.add(city(DURATION - ENDING), ENDING, 0.18)
# car section: rev + shifts + flybys
sfx.add(engine(3.2, 50, 260, 0.7, shift=[1.4, 2.5]), CAR, 0.95)
l, r = flyby(1.8); sfx.addst(l, r, b(19), 1.2)
sfx.add(engine(3.0, 120, 280, 0.8, shift=[1.2]), b(20), 0.8)
l, r = flyby(1.4); sfx.addst(r, l, b(25), 1.0)
# club: crowd murmur
sfx.add(bp(rng.standard_normal(int((CHASE - CLUB) * SR)), 250, 3000) * 0.05, CLUB, 1.0)
# chase: sirens (two cars, panned & detuned), engines, screeches
sfx.add(riser(CHASE - b(44)), b(44), 0.7)
sfx.add(siren(ENDING - CHASE + 1.0, "wail"), CHASE, 1.0, pan=-0.5)
sfx.add(siren(ENDING - CHASE + 0.5, "yelp") * 0.8, CHASE + 0.4, 0.7, pan=0.5)
sfx.add(engine(ENDING - CHASE, 150, 260, 1.0, shift=[2.0, 5.0, 8.0]), CHASE, 0.6)
sfx.add(screech(1.6), b(56), 1.0, pan=0.3)
sfx.add(screech(1.0), b(62), 1.0, pan=-0.3)
sfx.add(screech(0.6), b(68.5), 0.7)
l, r = flyby(1.2); sfx.addst(l, r, b(64), 1.0)
# ending: distant siren
sfx.add(lp(siren(DURATION - ENDING, "wail"), 1500), ENDING + 0.5, 0.35, pan=0.6)
sfx.add(impact(4.0), ENDCARD, 0.6)

L = ML * 0.9 + sfx.L; R = MR * 0.9 + sfx.R
# gentle bus compression (soft clip) + normalise
mx = max(np.abs(L).max(), np.abs(R).max())
L, R = np.tanh(1.2 * L / mx) , np.tanh(1.2 * R / mx)
L = L[:int(DURATION * SR)]; R = R[:int(DURATION * SR)]
fo = int(1.2 * SR); L[-fo:] *= np.linspace(1, 0, fo); R[-fo:] *= np.linspace(1, 0, fo)
pk = max(np.abs(L).max(), np.abs(R).max()); L *= 0.89 / pk; R *= 0.89 / pk
st = (np.stack([L, R], 1) * 32767).astype(np.int16)
with wave.open(sys.argv[1], 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(st.tobytes())
print("wrote", sys.argv[1], len(L) / SR, "s")
