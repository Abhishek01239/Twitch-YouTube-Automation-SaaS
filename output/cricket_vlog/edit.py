#!/usr/bin/env python3
"""Cinematic cricket-day vlog: edit decision list + full render pipeline.

Usage: python3 edit.py <src_dir> <work_dir> <out_dir>
Sources are the untouched Cloudinary originals VID-20261118-WA00xx.mp4.
"""
import json, os, subprocess, sys, wave
import numpy as np

SRC, WORK, OUT = sys.argv[1:4]
HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(WORK, exist_ok=True)
W, H, FPS, SR = 1080, 1920, 60, 48000

def src(n): return os.path.join(SRC, f"VID-20261118-WA00{n}.mp4")
def run(cmd): subprocess.run(cmd, check=True)

# ---------------------------------------------------------------- source fixes
# gain (dB): brings each source's natural sound to ~-16 LUFS (measured 03 -23.4,
# 04 -20.9, 07 -15.4, 08 -20.7, 09 -15.3).  eq: per-source match before the common look.
SRCFIX = {
    "03": dict(gain=7.0, eq="eq=contrast=1.08:saturation=1.42:gamma=0.97", shift=12),  # hazy, flat
    "04": dict(gain=4.9, eq="eq=contrast=1.02:saturation=0.88", shift=12),             # grass too yellow
    "07": dict(gain=-0.6, eq="eq=saturation=0.97", shift=18),
    "08": dict(gain=4.7, eq="eq=brightness=-0.03:contrast=1.04:saturation=1.18", shift=18),
    "09": dict(gain=-0.7, eq="eq=saturation=0.93", shift=18),
}
# common cinematic look: gentle warm sun, soft S-curve with lifted blacks / rolled highlights
LOOK = ("colorbalance=rs=0.015:bs=-0.02:rm=0.03:gm=0.005:bm=-0.03:rh=0.02:bh=-0.015,"
        "curves=all='0/0.025 0.25/0.235 0.5/0.5 0.75/0.775 1/0.975'")

# ---------------------------------------------------------------- edit decision list
# (id, src, in, out, speed, stabilise, natural-audio mode, gain, hits)
#  mode: sync = original sound in sync | amb = real-speed ambience | mute
#  hits: real-speed sound clips (src_in, src_out) placed on the matching slowed frame
S = lambda *a, **k: dict(zip(["id", "src", "a", "b", "speed", "stab", "mode", "gain"], a), hits=k.get("hits", []))
EDL = [
    # 1. OPENING — golden light, long shadow of the cameraperson, title
    S("O1", "04", 0.80, 4.00, 1.0, True, "amb", 0.35),
    S("O2", "03", 19.00, 21.80, 1.0, False, "amb", 0.30),   # batter waiting at the crease, tower behind
    # 2. FRIENDS / GETTING READY
    S("P1", "07", 2.90, 5.10, 1.0, False, "sync", 0.95),    # teammates join the selfie
    S("P2", "08", 2.00, 4.60, 1.0, False, "sync", 0.55),    # thumbs-up, walks out with the bat
    S("P3", "08", 8.00, 11.60, 1.0, False, "sync", 0.55),   # carrying & planting the stumps
    # 3. GROUND ATMOSPHERE
    S("G1", "04", 9.20, 12.60, 1.0, True, "sync", 0.40),    # wide: batter at the far crease
    S("G2", "04", 53.10, 54.80, 1.0, True, "sync", 0.40),   # low wide through tree shadows
    # 4. MAIN ACTION (music drop on A1a)
    S("A1a", "03", 10.60, 11.20, 1.0, False, "sync", 0.75),
    S("A1b", "03", 11.20, 12.50, 0.5, False, "mute", 0),    # big swing over the head, slow-mo
    S("A2", "03", 16.40, 18.40, 1.0, False, "sync", 0.75),  # forward drive
    S("A3", "04", 62.00, 64.95, 1.0, True, "sync", 0.70),   # wide angle, shot at 64.8
    S("A4", "09", 23.60, 26.50, 1.0, True, "sync", 0.70),   # nets: bowler runs in and delivers
    S("A5", "03", 29.40, 31.40, 1.0, False, "sync", 0.75),  # high backlift, shot
    S("A6a", "03", 37.60, 38.20, 1.0, False, "sync", 0.75),
    S("A6b", "03", 38.20, 39.60, 0.5, False, "mute", 0, hits=[(38.84, 39.30)]),  # ball in frame -> pull shot
    S("A7", "04", 73.40, 76.00, 1.0, True, "sync", 0.70),   # wide, shot at 75.4
    S("A8", "03", 44.80, 47.40, 1.0, False, "sync", 0.75),  # lofted shot, camera follows it into the sun
    S("A9", "03", 53.60, 55.50, 1.0, False, "sync", 0.75),
    S("A10", "03", 63.40, 65.60, 1.0, False, "sync", 0.75),
    S("A11", "09", 26.40, 29.60, 0.8, True, "amb", 0.55),   # bowler's arms-out celebration
    S("E1a", "03", 68.80, 69.35, 1.0, False, "sync", 0.80),
    S("E1b", "03", 69.35, 70.10, 0.5, False, "mute", 0, hits=[(69.46, 70.10)]),  # BOWLED — stumps fly
    S("E1c", "03", 70.10, 70.65, 1.0, False, "sync", 0.90),  # turns away laughing
    # 5. PERSONAL + CINEMATIC ENDING
    S("F1", "09", 9.60, 12.80, 1.0, False, "sync", 0.85),   # laughing selfie, sun flare
    S("E2", "04", 67.00, 71.00, 0.75, True, "amb", 0.22),   # calm wide of the ground, fade out
]
DISSOLVE = {"O2": 0.6, "E2": 1.0}   # dissolve INTO these segments; everything else is a clean cut

# ---------------------------------------------------------------- timeline
t = 0.0; prev_end = 0.0
for s in EDL:
    s["dur"] = round((s["b"] - s["a"]) / s["speed"] * FPS) / FPS
    s["start"] = prev_end - DISSOLVE.get(s["id"], 0.0)
    prev_end = s["start"] + s["dur"]
TOTAL = prev_end
seg = {s["id"]: s for s in EDL}
print(f"timeline: {len(EDL)} segments, {TOTAL:.2f}s")
for s in EDL:
    print(f"  {s['start']:6.2f}-{s['start'] + s['dur']:6.2f}  {s['id']:4} WA00{s['src']} {s['a']:.2f}-{s['b']:.2f} x{s['speed']}")

# ---------------------------------------------------------------- 1) per-segment video
for s in EDL:
    out = os.path.join(WORK, f"seg_{s['id']}.mp4")
    if os.path.exists(out) and os.environ.get("REUSE"):
        continue
    fx = SRCFIX[s["src"]]
    base = [f"trim=start={s['a']}:end={s['b']}", "setpts=(PTS-STARTPTS)/%s" % s["speed"]]
    chain = list(base)
    if s["stab"]:
        trf = os.path.join(WORK, f"{s['id']}.trf")
        run(["ffmpeg", "-v", "error", "-y", "-i", src(s["src"]), "-vf",
             ",".join(base + [f"vidstabdetect=shakiness=5:accuracy=15:result={trf}"]), "-f", "null", "-"])
        chain.append(f"vidstabtransform=input={trf}:smoothing=30:optzoom=1:maxshift={fx['shift']}:"
                     "maxangle=0.03:interpol=bicubic")
    if s["speed"] < 1:
        chain.append(f"minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")
    else:
        chain.append(f"fps={FPS}")
    chain += [fx["eq"], f"scale={W}:{H}:flags=lanczos", "setsar=1", LOOK,
              "unsharp=5:5:0.45:5:5:0", f"trim=duration={s['dur']}", "format=yuv420p"]
    run(["ffmpeg", "-v", "error", "-y", "-i", src(s["src"]), "-vf", ",".join(chain), "-an",
         "-c:v", "libx264", "-preset", "fast", "-crf", "12", "-r", str(FPS), out])
    print("rendered", s["id"])

# ---------------------------------------------------------------- 2) natural-sound bus
def load_audio(n):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src(n), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2) * 10 ** (SRCFIX[n]["gain"] / 20)
AUD = {n: load_audio(n) for n in SRCFIX}
nat = np.zeros((int((TOTAL + 1) * SR), 2))
def place(n, a, length, at, gain, fade=0.03):
    x = AUD[n][int(a * SR): int(a * SR) + int(length * SR)].copy() * gain
    f = min(int(fade * SR), len(x) // 2)
    if f: x[:f] *= np.linspace(0, 1, f)[:, None]; x[-f:] *= np.linspace(1, 0, f)[:, None]
    i = int(at * SR); nat[i:i + len(x)] += x[: len(nat) - i]
for s in EDL:
    fade = DISSOLVE.get(s["id"], 0.03) or 0.03
    if s["mode"] == "sync":
        place(s["src"], s["a"], s["dur"], s["start"], s["gain"])
    elif s["mode"] == "amb":
        place(s["src"], s["a"], s["dur"], s["start"], s["gain"], fade=max(fade, 0.3))
    for (ha, hb) in s["hits"]:
        place(s["src"], ha, hb - ha, s["start"] + (ha - s["a"]) / s["speed"], 0.95, fade=0.01)

# ---------------------------------------------------------------- 3) music, cued to the cut
stop = seg["E1b"]["start"] + (69.50 - seg["E1b"]["a"]) / seg["E1b"]["speed"]   # stump hit
markers = dict(end=round(TOTAL, 3), drop=round(seg["A1a"]["start"], 3), stop=round(stop, 3),
               outro=round(seg["F1"]["start"], 3),
               duck=[[seg["P1"]["start"], seg["P1"]["start"] + seg["P1"]["dur"]],
                     [seg["F1"]["start"], seg["F1"]["start"] + seg["F1"]["dur"]]])
markers["full"] = round(markers["drop"] * 2, 3)       # bar 16
json.dump(markers, open(os.path.join(WORK, "markers.json"), "w"))
music_wav = os.path.join(WORK, "music.wav")
run([sys.executable, os.path.join(HERE, "music.py"), os.path.join(WORK, "markers.json"), music_wav])
with wave.open(music_wav) as w:
    mus = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, 2) / 32767.0
# music level shape: settles in, peaks through the action, softens to the end
env = np.interp(np.arange(len(mus)) / SR,
                [0, markers["drop"] - 0.5, markers["drop"], markers["stop"], markers["outro"], TOTAL],
                [0.70, 0.76, 0.72, 0.78, 0.56, 0.46])
mus = mus * env[:, None]
mix = nat[: len(mus)] + mus
mix = np.clip(mix, -1.5, 1.5)
mix_wav = os.path.join(WORK, "mix.wav")
with wave.open(mix_wav, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(mix / max(1.0, np.abs(mix).max()), -1, 1) * 32767).astype(np.int16).tobytes())

# ---------------------------------------------------------------- 4) assemble picture
inputs = []; fc = []
for i, s in enumerate(EDL):
    inputs += ["-i", os.path.join(WORK, f"seg_{s['id']}.mp4")]
for i in range(len(EDL)):
    fc.append(f"[{i}:v]fps={FPS},settb=1/{FPS},setpts=N,format=yuv420p[n{i}]")
cur, cur_dur = "[n0]", EDL[0]["dur"]
for i, s in enumerate(EDL[1:], 1):
    lab = f"[c{i}]"
    if s["id"] in DISSOLVE:
        d = DISSOLVE[s["id"]]
        fc.append(f"{cur}[n{i}]xfade=transition=fade:duration={d}:offset={cur_dur - d:.4f}{lab}")
        cur_dur += s["dur"] - d
    else:
        fc.append(f"{cur}[n{i}]concat=n=2:v=1:a=0,settb=1/{FPS}{lab}")
        cur_dur += s["dur"]
    cur = lab
# title over the opening: two lines, letter-spaced, soft fade
def spaced(txt): return " ".join(txt).replace("   ", "    ")
open(os.path.join(WORK, "t1.txt"), "w").write(spaced("JUST ANOTHER"))
open(os.path.join(WORK, "t2.txt"), "w").write(spaced("CRICKET DAY"))
fade_expr = "if(lt(t,0.7),0,if(lt(t,1.5),(t-0.7)/0.8,if(lt(t,3.5),1,if(lt(t,4.3),(4.3-t)/0.8,0))))"
font = "/usr/share/fonts/opentype/inter/InterDisplay-"
title = (f"drawtext=fontfile={font}Regular.otf:textfile={WORK}/t1.txt:fontsize=56:fontcolor=white:"
         f"x=(w-text_w)/2:y=h*0.60:alpha='{fade_expr}':shadowcolor=black@0.55:shadowx=0:shadowy=3:enable='lt(t,4.4)',"
         f"drawtext=fontfile={font}SemiBold.otf:textfile={WORK}/t2.txt:fontsize=104:fontcolor=white:"
         f"x=(w-text_w)/2:y=h*0.60+84:alpha='{fade_expr}':shadowcolor=black@0.55:shadowx=0:shadowy=4:enable='lt(t,4.4)'")
fc.append(f"{cur}{title},vignette=angle=0.42:mode=forward,noise=c0s=3:c0f=t,"
          f"fade=t=in:d=0.7,fade=t=out:st={TOTAL - 1.8:.3f}:d=1.8,format=yuv420p[v]")
na = len(EDL)
fc.append(f"[{na}:a]afade=t=in:d=0.4,afade=t=out:st={TOTAL - 2.2:.3f}:d=2.2,"
          "acompressor=threshold=-18dB:ratio=2.5:attack=15:release=200:makeup=2,"
          "loudnorm=I=-14:TP=-1.5:LRA=9,aresample=48000[a]")
final = os.path.join(OUT, "cricket_cinematic_vlog.mp4")
run(["ffmpeg", "-v", "error", "-stats", "-y", *inputs, "-i", mix_wav, "-filter_complex", ";".join(fc),
     "-map", "[v]", "-map", "[a]", "-t", f"{TOTAL:.3f}", "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-maxrate", "14M", "-bufsize", "28M",
     "-profile:v", "high", "-level", "4.2", "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", "120",
     "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", final])
json.dump(dict(total=TOTAL, markers=markers, edl=[{k: v for k, v in s.items()} for s in EDL]),
          open(os.path.join(WORK, "timeline.json"), "w"), indent=1)
print("done", final)
