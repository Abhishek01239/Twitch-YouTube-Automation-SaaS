#!/usr/bin/env python3
"""ONE DAY. ONE GAME. — cinematic cricket short: shot list + full render pipeline.

Usage: python3 film.py <src_dir> <work_dir> <out_dir>
Sources: the untouched Cloudinary originals VID-20261118-WA00xx.mp4 (never modified).
"""
import json, math, os, subprocess, sys, wave
import numpy as np

SRC, WORK, OUT = sys.argv[1:4]
HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(WORK, exist_ok=True)
W, H, FPS, SR = 1080, 1920, 60, 48000
def src(n): return os.path.join(SRC, f"VID-20261118-WA00{n}.mp4")
def run(cmd): subprocess.run(cmd, check=True)

# ------------------------------------------------------------------ grade
# 1) per-source correction (exposure / white balance / haze) so every clip starts level
FIX = {
    "03": dict(gain=7.0, eq="eq=contrast=1.08:saturation=1.38:gamma=0.97,colorbalance=bm=-0.02", shift=12),
    "04": dict(gain=4.9, eq="eq=contrast=1.03:saturation=0.86,colorbalance=gm=-0.015", shift=12),
    "07": dict(gain=-0.6, eq="eq=saturation=0.95", shift=18),
    "08": dict(gain=4.7, eq="eq=brightness=-0.03:contrast=1.04:saturation=1.15", shift=18),
    "09": dict(gain=-0.7, eq="eq=saturation=0.92:contrast=1.02", shift=18),
}
# 2) the film's look: golden highlights, clean neutral-ish mids, soft filmic curve, protected skin
LOOK = ("colorbalance=rs=0.01:bs=-0.015:rm=0.025:gm=0.008:bm=-0.025:rh=0.045:gh=0.015:bh=-0.035,"
        "curves=all='0/0.03 0.22/0.20 0.5/0.5 0.78/0.80 1/0.97',vibrance=intensity=0.06")

# ------------------------------------------------------------------ shot list
# kind clip: speed (constant) or ramp=[(src_t, speed), ...] (piecewise-linear, smooth)
# audio: sync | amb (real-speed ambience) | mute ; lead = J-cut seconds (sound arrives early)
def clip(id, s, a, b, speed=1.0, ramp=None, stab=False, audio="sync", gain=0.7, hits=(), lead=0.0, crop=1.0):
    return dict(kind="clip", id=id, src=s, a=a, b=b, speed=speed, ramp=ramp, stab=stab, audio=audio,
                gain=gain, hits=list(hits), lead=lead, crop=crop)
def freeze(id, s, t, dur): return dict(kind="freeze", id=id, src=s, a=t, dur=dur, lead=0.0)
def black(id, dur): return dict(kind="black", id=id, dur=dur, lead=0.0)

SHOTS = [
    # ACT 1 — HOOK: black + isolated bat crack, the swing, the ball into the sun, freeze, title
    black("K0", 0.40),
    clip("K1", "03", 45.62, 46.30, gain=0.95),                                        # contact @46.06
    clip("K2", "03", 46.30, 47.82, ramp=[(46.30, 1), (46.62, 0.42), (47.82, 0.42)], audio="mute"),
    freeze("K3", "03", 47.82, 1.10),                                                   # sun + raised arm
    # ACT 2 — ARRIVAL: shadow walking onto the ground, walking out, stumps, waiting
    clip("R1", "04", 0.95, 3.85, stab=True, audio="amb", gain=0.40, lead=0.9),
    clip("R2", "08", 1.20, 4.40, gain=0.50),
    clip("R3", "08", 9.30, 12.60, gain=0.50),                                          # planting the stumps
    clip("R4", "03", 19.00, 21.50, audio="amb", gain=0.35),                            # yellow-stump match cut
    # ACT 3 — BUILD: wide stance, bowler runs in -> delivers -> celebrates, swing micro-montage
    clip("B1", "04", 9.20, 11.60, stab=True, gain=0.45),
    clip("B2", "09", 23.60, 26.35, stab=True, gain=0.65),
    clip("B3", "09", 26.35, 28.90, speed=0.82, stab=True, audio="amb", gain=0.55),     # arms-out celebration
    clip("B4", "03", 11.00, 12.60, ramp=[(11.0, 1), (11.25, 1), (11.45, 0.5), (12.15, 0.5), (12.38, 1), (12.6, 1)], audio="mute"),
    clip("B5", "03", 16.50, 18.30, gain=0.75),
    clip("B6", "04", 62.40, 64.95, stab=True, gain=0.70, crop=1.12),
    clip("B7", "03", 29.50, 31.20, gain=0.75),
    clip("B8", "03", 53.80, 55.40, gain=0.75),
    # ACT 4 — HERO: held breath (music out), ball arrives, ramp to slow, contact, freeze, snap back
    clip("H0", "03", 37.00, 38.20, audio="amb", gain=0.28),
    clip("H1", "03", 38.20, 39.30, ramp=[(38.2, 1), (38.36, 1), (38.54, 0.30), (39.30, 0.30)],
         audio="mute", hits=[(38.84, 39.25)]),
    freeze("H2", "03", 39.30, 0.55),
    clip("H3", "03", 39.30, 39.95, gain=0.85),                                          # sharp return to real time
    clip("H4", "04", 73.40, 76.00, stab=True, gain=0.70),
    clip("H5", "03", 63.40, 65.60, gain=0.75),
    # BOWLED — the stumps fly, the music stops, he walks away laughing
    clip("E1", "03", 68.80, 70.65, ramp=[(68.8, 1), (69.38, 1), (69.48, 0.35), (70.0, 0.35), (70.15, 1), (70.65, 1)],
         audio="mute", hits=[(69.46, 70.10)]),
    # ACT 5 — HUMAN: the people behind the game
    clip("M1", "07", 3.00, 5.00, gain=0.95, lead=0.45),
    clip("M2", "07", 6.70, 8.20, gain=0.90),
    clip("M3", "09", 9.60, 12.80, gain=0.85),
    # ACT 7 — ENDING: the ground, slowing down, the last line
    clip("Z1", "04", 67.00, 71.40, speed=0.72, stab=True, audio="amb", gain=0.30, lead=0.6),
]
DISSOLVE = {"Z1": 1.0}            # one dissolve into the last shot; everything else is a cut

# ------------------------------------------------------------------ time maps
def ramp_T(keys, s):
    """Output seconds elapsed at source time s for a piecewise-linear speed curve."""
    T = 0.0
    for (s0, v0), (s1, v1) in zip(keys, keys[1:]):
        if s <= s0: break
        e = min(s, s1); v_e = v0 + (v1 - v0) * (e - s0) / (s1 - s0)
        T += (e - s0) / v0 if abs(v1 - v0) < 1e-9 else (s1 - s0) / (v1 - v0) * math.log(v_e / v0)
    return T
def ramp_expr(keys):
    """setpts expression (input T = source seconds from clip start) -> output timestamp."""
    a0 = keys[0][0]; parts = []; Tacc = 0.0
    for (s0, v0), (s1, v1) in zip(keys, keys[1:]):
        r0, r1 = s0 - a0, s1 - a0
        if abs(v1 - v0) < 1e-9: f = f"({Tacc:.6f}+(T-{r0:.6f})/{v0})"
        else:
            k = (r1 - r0) / (v1 - v0)
            f = f"({Tacc:.6f}+{k:.6f}*log(({v0}+({v1 - v0:.6f})*(T-{r0:.6f})/{r1 - r0:.6f})/{v0}))"
        parts.append((r1, f)); Tacc += ramp_T([(s0, v0), (s1, v1)], s1)
    expr = parts[-1][1]
    for r1, f in reversed(parts[:-1]): expr = f"if(lt(T,{r1:.6f}),{f},{expr})"
    return expr
def out_time(sh, s):
    return ramp_T(sh["ramp"], s) if sh.get("ramp") else (s - sh["a"]) / sh["speed"]

t = 0.0
for sh in SHOTS:
    if sh["kind"] == "clip": dur = out_time(sh, sh["b"])
    else: dur = sh["dur"]
    sh["dur"] = round(dur * FPS) / FPS
    sh["start"] = t - DISSOLVE.get(sh["id"], 0.0); t = sh["start"] + sh["dur"]
TOTAL = t + 0.0
S = {sh["id"]: sh for sh in SHOTS}
print(f"film: {len(SHOTS)} shots, {TOTAL:.2f}s")
for sh in SHOTS:
    info = f"WA00{sh['src']} {sh['a']:.2f}-{sh.get('b', sh['a']):.2f}" if sh["kind"] != "black" else ""
    print(f"  {sh['start']:6.2f}-{sh['start'] + sh['dur']:6.2f} {sh['id']:3} {sh['kind']:6} {info}"
          f"{' ramp' if sh.get('ramp') else ''}{' x%.2f' % sh['speed'] if sh.get('speed', 1) != 1 else ''}")

# ------------------------------------------------------------------ 1) render shots
def finish(chain, fx):
    return chain + [fx["eq"], f"scale={W}:{H}:flags=lanczos", "setsar=1", LOOK, "unsharp=5:5:0.4:5:5:0"]
for sh in SHOTS:
    out = os.path.join(WORK, f"shot_{sh['id']}.mp4")
    if os.environ.get("REUSE") and os.path.exists(out): continue
    if sh["kind"] == "black":
        run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=black:s={W}x{H}:r={FPS}:d={sh['dur']}",
             "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", out]); continue
    fx = FIX[sh["src"]]
    if sh["kind"] == "freeze":
        chain = [f"trim=start={sh['a'] - 0.02}", "setpts=PTS-STARTPTS", "trim=end_frame=1",
                 f"tpad=stop_mode=clone:stop_duration={sh['dur'] + 0.1}", f"fps={FPS}"]
    else:
        chain = [f"trim=start={sh['a']}:end={sh['b']}", "setpts=PTS-STARTPTS"]
        if sh["ramp"]: chain.append(f"setpts='{ramp_expr(sh['ramp'])}/TB'")
        elif sh["speed"] != 1: chain.append(f"setpts=PTS/{sh['speed']}")
        if sh["stab"]:
            trf = os.path.join(WORK, f"{sh['id']}.trf")
            run(["ffmpeg", "-v", "error", "-y", "-i", src(sh["src"]), "-vf",
                 ",".join(chain + [f"vidstabdetect=shakiness=5:accuracy=15:result={trf}"]), "-f", "null", "-"])
            chain.append(f"vidstabtransform=input={trf}:smoothing=30:optzoom=1:maxshift={fx['shift']}:maxangle=0.03")
        if sh["ramp"] or sh["speed"] != 1:
            chain.append(f"minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")
        else:
            chain.append(f"fps={FPS}")
        if sh["crop"] > 1:
            c = sh["crop"]; chain.append(f"crop=iw/{c}:ih/{c}:(iw-iw/{c})/2:(ih-ih/{c})*0.55")
    chain = finish(chain, fx) + ["tpad=stop_mode=clone:stop_duration=0.5", f"trim=end_frame={round(sh['dur'] * FPS)}", f"setpts=N/({FPS}*TB)", "format=yuv420p"]
    run(["ffmpeg", "-v", "error", "-y", "-i", src(sh["src"]), "-vf", ",".join(chain), "-an", "-fps_mode", "passthrough",
         "-c:v", "libx264", "-preset", "fast", "-crf", "12", "-video_track_timescale", str(FPS * 1000), out])
    print("shot", sh["id"], flush=True)

# ------------------------------------------------------------------ 2) natural sound (with J-cuts)
def load(n):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src(n), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2) * 10 ** (FIX[n]["gain"] / 20)
AUD = {n: load(n) for n in FIX}
LEN = int((TOTAL + 1) * SR)
nat = np.zeros((LEN, 2)); sfx = np.zeros((LEN, 2))
def place(bus, x, at, g=1.0, fin=0.03, fout=0.03):
    x = x * g; a, b = min(int(fin * SR), len(x) // 2), min(int(fout * SR), len(x) // 2)
    if a: x[:a] *= np.linspace(0, 1, a)[:, None]
    if b: x[-b:] *= np.linspace(1, 0, b)[:, None]
    i = int(at * SR)
    if i < 0: x, i = x[-i:], 0
    bus[i:i + len(x)] += x[: LEN - i]
def src_audio(n, a, d): return AUD[n][int(a * SR): int(a * SR) + int(d * SR)].copy()
for sh in SHOTS:
    if sh["kind"] != "clip": continue
    lead = min(sh["lead"], sh["a"])
    if sh["audio"] == "sync" and not sh["ramp"] and sh["speed"] == 1:
        place(nat, src_audio(sh["src"], sh["a"] - lead, sh["dur"] + lead), sh["start"] - lead, sh["gain"],
              fin=max(lead, 0.03))
    elif sh["audio"] == "amb":
        place(nat, src_audio(sh["src"], sh["a"] - lead, sh["dur"] + lead), sh["start"] - lead, sh["gain"],
              fin=max(lead, 0.25), fout=0.25)
    if sh["ramp"]:   # real-speed stretches of a ramp keep their own sound, in sync
        for (s0, v0), (s1, v1) in zip(sh["ramp"], sh["ramp"][1:]):
            if v0 == 1 and v1 == 1:
                place(nat, src_audio(sh["src"], s0, s1 - s0), sh["start"] + out_time(sh, s0), 0.75)
    for (ha, hb) in sh["hits"]:
        place(nat, src_audio(sh["src"], ha, hb - ha), sh["start"] + out_time(sh, ha), 0.95, fin=0.005)

# ------------------------------------------------------------------ 3) sound design (synthesised)
rng = np.random.default_rng(5)
def tt(d): return np.arange(int(d * SR)) / SR
def bandnoise(d, lo, hi):
    x = rng.uniform(-1, 1, int(d * SR)); X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(X * ((f > lo) & (f < hi)), len(x))
def whoosh(d, peak=0.7):   # air past the mic, motivated by a swing / camera move
    x = bandnoise(d, 300, 6000); e = np.interp(tt(d), [0, d * peak, d], [0, 1, 0]) ** 1.6
    return np.stack([x * e, np.roll(x, 240) * e], 1) * 0.6
def boom(d=2.2, f0=48):    # low cinematic accent under an impact
    t = tt(d); f = f0 + 30 * np.exp(-t * 12)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.2) * np.minimum(1, t / 0.004)
    return np.stack([x, x], 1)
def shimmer(d=2.5):        # airy tail behind a freeze frame
    x = bandnoise(d, 5000, 12000) * np.exp(-tt(d) * 2.0) * np.minimum(1, tt(d) / 0.3)
    return np.stack([x, np.roll(x, 500)], 1) * 0.5
hit_hook = S["K1"]["start"] + (46.06 - S["K1"]["a"])
place(sfx, whoosh(0.45, 0.95), 0.0, 0.10)                         # into the first cut
place(sfx, boom(), hit_hook, 0.28)
place(sfx, shimmer(2.2), S["K3"]["start"], 0.10)
place(sfx, boom(2.6, 40), S["K3"]["start"], 0.22)                  # title lands
place(sfx, whoosh(0.5), S["B4"]["start"] + 0.15, 0.08)            # swing ramp
hit_hero = S["H1"]["start"] + out_time(S["H1"], 38.84)
place(sfx, whoosh(0.9, 0.85), hit_hero - 0.75, 0.09)
place(sfx, boom(2.8, 44), hit_hero, 0.45)
place(sfx, shimmer(1.5), S["H2"]["start"], 0.08)
stump = S["E1"]["start"] + out_time(S["E1"], 69.50)
place(sfx, boom(1.8, 55), stump, 0.25)

# ------------------------------------------------------------------ 4) score, cued to picture
cues = dict(hook=0.0, title=round(S["K3"]["start"], 3), arrival=round(S["R1"]["start"], 3),
            build=round(S["B1"]["start"], 3), pause=round(S["H0"]["start"], 3),
            hero=round(S["H3"]["start"], 3), stop=round(stump, 3), human=round(S["M1"]["start"] - 0.4, 3),
            ending=round(S["Z1"]["start"], 3), end=round(TOTAL, 3))
json.dump(cues, open(os.path.join(WORK, "cues.json"), "w"))
run([sys.executable, os.path.join(HERE, "score.py"), os.path.join(WORK, "cues.json"), os.path.join(WORK, "score.wav")])
with wave.open(os.path.join(WORK, "score.wav")) as w:
    mus = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, 2) / 32767.0
tm = np.arange(len(mus)) / SR
menv = np.interp(tm, [0, cues["arrival"], cues["build"], cues["pause"], cues["hero"], cues["stop"],
                      S["M1"]["start"], S["M3"]["start"] + S["M3"]["dur"], cues["ending"], TOTAL],
                     [0.8, 0.70, 0.72, 0.85, 0.95, 0.95, 0.45, 0.45, 0.70, 0.60])
mus = mus * menv[:, None]
mix = nat[: len(mus)] * 1.0 + sfx[: len(mus)] + mus
peak = np.abs(mix).max()
with wave.open(os.path.join(WORK, "mix.wav"), "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((mix / max(peak, 1e-9) * 0.95 * 32767).astype(np.int16).tobytes())

# ------------------------------------------------------------------ 5) assemble picture + titles
inputs, fc = [], []
for i, sh in enumerate(SHOTS):
    inputs += ["-i", os.path.join(WORK, f"shot_{sh['id']}.mp4")]
    fc.append(f"[{i}:v]fps={FPS},settb=1/{FPS},setpts=N,format=yuv420p[n{i}]")
cur, cur_d = "[n0]", SHOTS[0]["dur"]
for i, sh in enumerate(SHOTS[1:], 1):
    if sh["id"] in DISSOLVE:
        d = DISSOLVE[sh["id"]]
        fc.append(f"{cur}[n{i}]xfade=transition=fade:duration={d}:offset={cur_d - d:.4f}[c{i}]"); cur_d += sh["dur"] - d
    else:
        fc.append(f"{cur}[n{i}]concat=n=2:v=1:a=0,settb=1/{FPS}[c{i}]"); cur_d += sh["dur"]
    cur = f"[c{i}]"
FONT = "/usr/share/fonts/opentype/inter/InterDisplay-"
def spaced(s): return " ".join(s).replace("   ", "    ")
def title(name, text, t0, t1, y, size, weight="Light", fade=0.6, drift=10):
    p = os.path.join(WORK, f"{name}.txt"); open(p, "w").write(spaced(text))
    a = f"if(lt(t,{t0}),0,if(lt(t,{t0 + fade}),(t-{t0})/{fade},if(lt(t,{t1 - fade}),1,if(lt(t,{t1}),({t1}-t)/{fade},0))))"
    yy = f"{y}-{drift}*min(1,(t-{t0})/{t1 - t0})"
    return (f"drawtext=fontfile={FONT}{weight}.otf:textfile={p}:fontsize={size}:fontcolor=white@0.94:"
            f"x=(w-text_w)/2:y='{yy}':alpha='{a}':shadowcolor=black@0.6:shadowx=0:shadowy=2:"
            f"enable='between(t,{t0},{t1})'")
k3 = S["K3"]["start"]; z1 = S["Z1"]["start"]
titles = [title("t_hook", "WE CAME FOR A GAME.", k3 - 0.9, S["R1"]["start"] + 0.15, int(H * 0.33), 58, "Regular", 0.5, 8),
          title("t_end1", "NOT EVERY GREAT DAY", z1 + 1.4, TOTAL - 0.5, int(H * 0.63), 50, "Regular"),
          title("t_end2", "NEEDS A SCOREBOARD.", z1 + 1.9, TOTAL - 0.5, int(H * 0.63) + 70, 50, "Regular")]
# bloom: soft glow lifted from the highlights only (sunlight feel), then vignette + fine grain
fc.append(f"{cur}split[base][hl];[hl]curves=all='0/0 0.72/0 1/0.85',gblur=sigma=28[glow];"
          f"[base][glow]blend=all_mode=screen:all_opacity=0.22,{','.join(titles)},"
          f"vignette=angle=0.40,noise=c0s=3:c0f=t,"
          f"fade=t=out:st={TOTAL - 1.6:.3f}:d=1.6,format=yuv420p[v]")
fc.append(f"[{len(SHOTS)}:a]afade=t=out:st={TOTAL - 2.0:.3f}:d=2.0,"
          "acompressor=threshold=-20dB:ratio=2.2:attack=10:release=180:makeup=1.5,"
          "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")
final = os.path.join(OUT, "cricket_film_final.mp4")
run(["ffmpeg", "-v", "error", "-stats", "-y", *inputs, "-i", os.path.join(WORK, "mix.wav"),
     "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]", "-t", f"{TOTAL:.3f}",
     "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-maxrate", "14M", "-bufsize", "28M",
     "-profile:v", "high", "-level", "4.2", "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", "120",
     "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", final])
json.dump(dict(total=TOTAL, cues=cues, shots=SHOTS), open(os.path.join(WORK, "timeline.json"), "w"), indent=1, default=str)
print("done", final, f"{TOTAL:.2f}s")
