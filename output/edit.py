#!/usr/bin/env python3
"""Edit decision list + ffmpeg render for the cricket-practice montage.

Usage: python3 edit.py <src_dir> <out_dir>
Source files are the untouched originals downloaded from Cloudinary.
"""
import subprocess, sys, os

SRC, OUT = sys.argv[1], sys.argv[2]
W, H, FPS = 720, 1280, 60

# Per-source corrections: gain (dB) brings each clip's integrated loudness to ~-16 LUFS
# (measured: 03=-23.4, 04=-20.9, 07=-15.4, 08=-20.7, 09=-15.3); eq matches colour.
SOURCES = {
    "07": dict(gain=-0.6, eq=None),
    "08": dict(gain=4.7, eq="eq=brightness=-0.03:contrast=1.04:saturation=1.3"),
    "03": dict(gain=7.0, eq="eq=contrast=1.06:saturation=1.55"),
    "04": dict(gain=4.9, eq=None),
    "09": dict(gain=-0.7, eq=None),
}

# Act 1 — morning session, ground A (hard cuts)
ACT1 = [
    ("07", 0.00, 17.40),   # selfie intro: sets up the session
    ("08", 0.00, 13.60),   # thumbs-up, carrying & planting the stumps
    ("03", 0.40, 2.95),    # POV behind stumps: first shot
    ("03", 6.00, 11.00),   # shot at ~10s
    ("03", 13.00, 16.90),  # shot at ~15.8s
    ("03", 26.80, 33.00),  # two deliveries, shots at ~28s and ~32s
    ("03", 37.00, 40.50),  # ball visible in frame, shot at ~38s
    ("03", 43.50, 46.60),  # shot at ~46s
    ("03", 51.00, 55.40),  # shot at ~54.8s
    ("03", 61.50, 70.60),  # new low angle, run of shots to the end
]
# Act 2 — afternoon session, ground B (one dissolve into it, then hard cuts)
ACT2 = [
    ("04", 9.00, 19.20),   # wide shot of batting
    ("04", 31.50, 34.50),  # shot at ~32s
    ("04", 59.50, 65.60),  # shot at ~64.8s
    ("04", 70.00, 76.60),  # shot at ~75.2s
    ("09", 22.30, 32.60),  # bowling in the nets, arms-out celebration
    ("09", 8.60, 14.80),   # laughing selfie as the outro
]
XFADE = 0.6  # seconds, the only transition (change of ground / time of day)

inputs = sorted({s for s, _, _ in ACT1 + ACT2})
idx = {s: i for i, s in enumerate(inputs)}
args = ["ffmpeg", "-y", "-v", "error", "-stats"]
for s in inputs:
    args += ["-i", os.path.join(SRC, f"VID-20261118-WA00{s}.mp4")]

f = []
def seg(name, s, a, b):
    d = b - a
    vchain = [f"trim=start={a}:end={b}", "setpts=PTS-STARTPTS", f"fps={FPS}",
              f"scale={W}:{H}:flags=lanczos", "setsar=1"]
    if SOURCES[s]["eq"]:
        vchain.append(SOURCES[s]["eq"])
    vchain.append("format=yuv420p")
    f.append(f"[{idx[s]}:v]{','.join(vchain)}[{name}v]")
    f.append(f"[{idx[s]}:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,aresample=48000,"
             f"aformat=channel_layouts=stereo,volume={SOURCES[s]['gain']}dB,"
             f"afade=t=in:d=0.03,afade=t=out:st={d-0.04:.3f}:d=0.04[{name}a]")
    return d

def group(segs, tag):
    total = 0
    labels = ""
    for i, (s, a, b) in enumerate(segs):
        n = f"{tag}{i}"
        total += seg(n, s, a, b)
        labels += f"[{n}v][{n}a]"
    f.append(f"{labels}concat=n={len(segs)}:v=1:a=1[{tag}v][{tag}a]")
    return total

d1 = group(ACT1, "A")
d2 = group(ACT2, "B")
total = d1 + d2 - XFADE
f.append(f"[Av][Bv]xfade=transition=fade:duration={XFADE}:offset={d1-XFADE:.3f}[xv]")
f.append(f"[Aa][Ba]acrossfade=d={XFADE}[xa]")
f.append(f"[xv]fade=t=in:d=0.5,fade=t=out:st={total-1.0:.3f}:d=1.0[outv]")
# final loudness: -14 LUFS (social-video target), true-peak limited
f.append(f"[xa]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,"
         f"afade=t=in:d=0.3,afade=t=out:st={total-1.2:.3f}:d=1.2[outa]")

final = os.path.join(OUT, "final_video.mp4")
args += ["-filter_complex", ";".join(f), "-map", "[outv]", "-map", "[outa]",
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high",
         "-r", str(FPS), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
         "-ar", "48000", "-movflags", "+faststart", final]
print(f"Act1 {d1:.2f}s  Act2 {d2:.2f}s  expected total {total:.2f}s")
subprocess.run(args, check=True)
