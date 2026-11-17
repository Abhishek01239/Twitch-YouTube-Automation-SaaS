"""Automated QC of the final render. Writes 02_analysis/qc_report.txt and a contact sheet."""
import json, os, re, subprocess, sys

P = os.path.abspath(sys.argv[1])
F = os.path.join(P, "06_final", "Final_Edited_Video.mp4")
out = []


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def log(s):
    print(s); out.append(s)


pr = json.loads(sh(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", F]).stdout)
v = [s for s in pr["streams"] if s["codec_type"] == "video"][0]
a = [s for s in pr["streams"] if s["codec_type"] == "audio"][0]
log(f"file: {F}  size {int(pr['format']['size'])/1e6:.1f} MB")
log(f"video: {v['codec_name']} {v['width']}x{v['height']} {v['r_frame_rate']} fps, {v['pix_fmt']}, dur {float(v['duration']):.3f}s")
log(f"audio: {a['codec_name']} {a['sample_rate']} Hz {a['channels']}ch, dur {float(a['duration']):.3f}s")
drift = abs(float(v["duration"]) - float(a["duration"]))
log(f"A/V duration difference: {drift*1000:.0f} ms -> {'OK' if drift < 0.1 else 'CHECK'}")

# 1. full decode — any corrupt packet / decode error shows up here
r = sh(["ffmpeg", "-v", "error", "-i", F, "-f", "null", "-"])
log(f"full decode errors: {len(r.stderr.strip().splitlines()) if r.stderr.strip() else 0}")

# 2. black frames, frozen frames
r = sh(["ffmpeg", "-i", F, "-vf", "blackdetect=d=0.4:pix_th=0.06,freezedetect=n=0.002:d=3", "-an", "-f", "null", "-"])
blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr)
freezes = re.findall(r"freeze_start: ([\d.]+)", r.stderr)
log(f"black segments >=0.4s: {len(blacks)}")
for b in blacks:
    log(f"   black {float(b[0]):8.2f} -> {float(b[1]):8.2f}")
log(f"frozen segments >=3s: {len(freezes)} {freezes[:10]}")

# 3. loudness (target -14 LUFS integrated, TP <= -1)
r = sh(["ffmpeg", "-i", F, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
tail = r.stderr[r.stderr.rfind("Summary:"):]
I = re.search(r"I:\s+(-?[\d.]+) LUFS", tail); TP = re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail)
LRA = re.search(r"LRA:\s+([\d.]+) LU", tail)
log(f"loudness: integrated {I.group(1) if I else '?'} LUFS, true peak {TP.group(1) if TP else '?'} dBFS, LRA {LRA.group(1) if LRA else '?'} LU")

# 4. caption / title text spell check (aspell if present, else word list printed for manual review)
ass = open(os.path.join(P, "05_work", "clips", "overlay.ass"), encoding="utf-8").read()
texts = [re.sub(r"\{[^}]*\}", "", l.split(",,0,0,0,,", 1)[1]).replace(r"\N", " ")
         for l in ass.splitlines() if l.startswith("Dialogue:")]
words = sorted({w for t in texts for w in re.findall(r"[A-Za-z']+", t)})
r = sh(["bash", "-c", "command -v aspell"])
if r.stdout.strip():
    bad = sh(["aspell", "list", "--lang=en"], ) if False else subprocess.run(["aspell", "list", "--lang=en"], input=" ".join(words), capture_output=True, text=True).stdout.split()
    log(f"spell check (aspell): unknown words = {sorted(set(bad))}")
else:
    log("spell check: aspell not installed; caption words listed for manual review")
log("on-screen text (" + str(len(texts)) + " events):")
for t in texts:
    log("   " + t)

# 5. contact sheet of the final (1 frame / 12 s)
sheet = os.path.join(P, "02_analysis", "final_contact_sheet_%02d.jpg")
sh(["ffmpeg", "-y", "-v", "error", "-i", F, "-vf",
    "fps=1/12,scale=320:-2,drawtext=text='%{pts\\:hms}':x=4:y=4:fontsize=18:fontcolor=yellow:box=1:boxcolor=black@0.6,tile=6x5",
    sheet])
open(os.path.join(P, "02_analysis", "qc_report.txt"), "w").write("\n".join(out) + "\n")
