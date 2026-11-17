"""Render engine: EDL (JSON) -> per-clip renders -> concat -> music/SFX mix -> captions/titles -> final MP4.

Usage: python3 render.py <project_dir> [--preview]
Reads  <project_dir>/03_scripts/edl.json
Writes <project_dir>/05_work/... and <project_dir>/06_final/Final_Edited_Video.mp4
"""
import json, os, subprocess, sys

P = os.path.abspath(sys.argv[1])
PREVIEW = "--preview" in sys.argv
EDL = json.load(open(os.path.join(P, "03_scripts", "edl.json")))
SRC = os.path.join(P, EDL["source"])
W, H, FPS = (960, 540, 30) if PREVIEW else (1920, 1080, 30)
WORK = os.path.join(P, "05_work", "preview" if PREVIEW else "clips")
os.makedirs(WORK, exist_ok=True)
A = os.path.join(P, "04_assets")


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(" ".join(cmd)); print(r.stderr[-3000:]); sys.exit(1)
    return r


# ------------------------------------------------------------------ colour grades
GRADES = {
    # warm, slightly desaturated daylight with gentle contrast
    "day":   "eq=contrast=1.06:saturation=0.88:gamma=0.98,colorbalance=rs=0.02:bs=-0.03:rh=0.03:bh=-0.02",
    # pink room: tame the magenta walls, add a cooler horror tint
    "room":  "eq=contrast=1.08:saturation=0.78:gamma=0.97,colorbalance=rm=-0.04:bm=0.02:rs=-0.02:bs=0.03",
    # golden-hour dusk: keep warmth in highlights, cool the shadows (teal/orange)
    "dusk":  "eq=contrast=1.08:saturation=0.92,colorbalance=rs=-0.04:bs=0.05:rh=0.05:bh=-0.04",
    # night interior: lift shadows slightly, cold desaturated look
    "night": "eq=contrast=1.10:saturation=0.72:gamma=1.06:brightness=0.01,colorbalance=rs=-0.03:gs=0.0:bs=0.05:rm=-0.02:bm=0.03",
    "none":  "null",
}
FINISH = "vignette=angle=PI/5:mode=forward"


def clip_filters(c, dur_out):
    """Video filter chain for one clip (input is the trimmed source segment)."""
    f = []
    sp = c.get("speed", 1.0)
    # light denoise before the 3x upscale, then sharpen after
    f.append("hqdn3d=1.5:1.5:4:4")
    if c.get("slowmo"):
        # motion-compensated slow motion: interpolate to fps/speed then retime
        f.append(f"minterpolate=fps={int(FPS / sp)}:mi_mode=mci:mc_mode=aobmc:vsbmc=1")
        f.append(f"setpts=PTS/{sp}" if False else f"setpts={1/sp:.4f}*PTS")
    elif sp != 1.0:
        f.append(f"setpts={1/sp:.4f}*PTS")
    f.append(f"fps={FPS}")
    z = c.get("zoom")  # e.g. 0.06 => push in 6% over the clip; negative = pull out
    big_w, big_h = int(W * 1.2) // 2 * 2, int(H * 1.2) // 2 * 2
    if z:
        f.append(f"scale={big_w}:{big_h}:flags=lanczos")
        z0, z1 = (1.0, 1.0 + z) if z > 0 else (1.0 - z, 1.0)
        zexpr = f"({z0}+({z1}-{z0})*min(t/{dur_out:.3f}\\,1))"
        cx = c.get("zoom_cx", 0.5); cy = c.get("zoom_cy", 0.5)
        f.append(f"crop=w='trunc({big_w}/{zexpr}/2)*2':h='trunc({big_h}/{zexpr}/2)*2'"
                 f":x='({big_w}-out_w)*{cx}':y='({big_h}-out_h)*{cy}'")
    f.append(f"scale={W}:{H}:flags=lanczos,setsar=1")
    f.append("unsharp=5:5:0.6:5:5:0.0")
    f.append(GRADES[c.get("grade", "none")])
    f.append(FINISH)
    fi, fo = c.get("fade_in", 0), c.get("fade_out", 0)
    if fi:
        f.append(f"fade=t=in:st=0:d={fi}")
    if fo:
        f.append(f"fade=t=out:st={dur_out - fo:.3f}:d={fo}")
    f.append("format=yuv420p")
    return ",".join(f)


def audio_filters(c, dur_out):
    sp = c.get("speed", 1.0)
    f = ["highpass=f=80", "afftdn=nr=10:nf=-40",  # rumble + broadband noise reduction
         "equalizer=f=3000:t=q:w=1.2:g=3",         # presence lift for dialogue clarity
         "acompressor=threshold=-24dB:ratio=3:attack=8:release=120:makeup=4"]
    if sp != 1.0:
        f.append(f"atempo={sp}" if 0.5 <= sp <= 2 else f"atempo={sp**0.5},atempo={sp**0.5}")
    g = c.get("orig_gain_db", 0)
    if c.get("mute"):
        f.append("volume=0")
    elif g:
        f.append(f"volume={g}dB")
    # short fades at every cut to avoid clicks (plus any requested longer fade)
    fi = max(c.get("fade_in", 0), 0.02); fo = max(c.get("fade_out", 0), 0.03)
    f.append(f"afade=t=in:st=0:d={fi}")
    f.append(f"afade=t=out:st={dur_out - fo:.3f}:d={fo}")
    f.append("aresample=48000,aformat=channel_layouts=stereo")
    return ",".join(f)


def voice_filters(c, dur_out):
    """Dialogue chain for the separately-built voice track (input already de-noised by
    enhance_voice.py): clean low end, cut mud, add presence/air, tame sibilance, level."""
    sp = c.get("speed", 1.0)
    f = ["highpass=f=90:poles=2",
         "equalizer=f=250:t=q:w=1.0:g=-3",     # boxy / muddy phone-mic low mids
         "equalizer=f=3200:t=q:w=1.4:g=4",     # intelligibility / presence
         "equalizer=f=7000:t=q:w=1.0:g=1.5",   # a little air back after de-noising
         "deesser=i=0.4:m=0.5:f=0.5",
         "acompressor=threshold=-28dB:ratio=3.5:attack=6:release=150:makeup=6:knee=4"]
    if sp != 1.0:
        f.append(f"atempo={sp}" if 0.5 <= sp <= 2 else f"atempo={sp**0.5},atempo={sp**0.5}")
    g = c.get("orig_gain_db", 0)
    if c.get("mute"):
        f.append("volume=0")
    elif g:
        f.append(f"volume={g}dB")
    fi = max(c.get("fade_in", 0), 0.02); fo = max(c.get("fade_out", 0), 0.03)
    f.append(f"afade=t=in:st=0:d={fi}")
    f.append(f"afade=t=out:st={dur_out - fo:.3f}:d={fo}")
    # pad/trim to the clip's exact rendered video duration so the track stays frame-accurate
    f.append(f"aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:{c['_dur']:.6f}")
    return ",".join(f)


def build_dialogue(clips):
    """Per-clip voice audio from the enhanced soundtrack, concatenated into one WAV."""
    src = os.path.join(P, EDL["dialogue_audio"])
    vdir = os.path.join(WORK, "voice"); os.makedirs(vdir, exist_ok=True)
    parts = []
    for i, c in enumerate(clips):
        o = os.path.join(vdir, f"v_{i:03d}.wav")
        if c.get("card"):
            run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                 "-t", f"{c['_dur']:.6f}", "-c:a", "pcm_s16le", o])
        else:
            sp = c.get("speed", 1.0)
            dur_in = c["out"] - c["in"]
            run(["ffmpeg", "-y", "-v", "error", "-ss", f"{c['in']:.3f}", "-t", f"{dur_in:.3f}", "-i", src,
                 "-af", voice_filters(c, dur_in / sp), "-c:a", "pcm_s16le", o])
        parts.append(o)
    lst = os.path.join(vdir, "list.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    out = os.path.join(WORK, "dialogue.wav")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out])
    return out


def render_clip(i, c):
    import hashlib
    key = hashlib.md5(json.dumps({k: v for k, v in c.items() if k not in ("text", "captions", "label") and not k.startswith("_")},
                                 sort_keys=True).encode() + f"{W}x{H}".encode()).hexdigest()[:10]
    out = os.path.join(WORK, f"clip_{key}.mp4")
    sp = c.get("speed", 1.0)
    dur_in = c["out"] - c["in"]
    dur_out = dur_in / sp
    c["_dur"] = dur_out
    if c.get("card"):  # generated black card (title / chapter); text is added by ASS later
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d={c['card']}",
               "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo", "-t", str(c["card"]),
               "-c:v", "libx264", "-preset", "veryfast" if PREVIEW else "medium", "-crf", "18", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "192k", out]
        c["_dur"] = c["card"]
    else:
        cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{c['in']:.3f}", "-t", f"{dur_in:.3f}", "-i", SRC,
               "-vf", clip_filters(c, dur_out), "-af", audio_filters(c, dur_out),
               "-t", f"{dur_out:.3f}", "-r", str(FPS),
               "-c:v", "libx264", "-preset", "veryfast" if PREVIEW else "medium", "-crf", "18",
               "-c:a", "aac", "-b:a", "192k", "-ar", "48000", out]
    if not os.path.exists(out):  # cache: identical clip settings are never re-rendered
        run(cmd[:-1] + [out + ".part.mp4"])
        os.replace(out + ".part.mp4", out)
    # use the real rendered duration (frame-rounded) for timeline maths
    d = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out]).stdout)
    c["_dur"] = d
    return out


def ts(t):
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_ass(clips, path):
    """Title cards, chapter lower-thirds and animated dialogue captions in one ASS file."""
    sc = H / 1080
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,{EDL['fonts']['title']},{int(150*sc)},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,{int(14*sc)},0,1,0,{int(6*sc)},5,0,0,0,1
Style: Kicker,{EDL['fonts']['ui']},{int(64*sc)},&H00D2D2D2,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,{int(5*sc)},0,1,0,0,5,0,0,0,1
Style: Chapter,{EDL['fonts']['ui']},{int(56*sc)},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,{int(6*sc)},0,1,0,{int(2*sc)},1,{int(90*sc)},0,{int(90*sc)},1
Style: ChapterNum,{EDL['fonts']['ui']},{int(32*sc)},&H002A2AE0,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,{int(8*sc)},0,1,0,0,1,{int(90*sc)},0,{int(140*sc)},1
Style: Cap,{EDL['fonts']['caption']},{int(54*sc)},&H00FFFFFF,&H0000E5FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{int(4*sc)},{int(2*sc)},2,{int(120*sc)},{int(120*sc)},{int(70*sc)},1
Style: Note,{EDL['fonts']['ui']},{int(28*sc)},&H00DCDCDC,&H000000FF,&H00000000,&H80000000,0,1,0,0,100,100,{int(3*sc)},0,1,0,{int(2*sc)},9,0,{int(50*sc)},{int(40*sc)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    t = 0.0
    for c in clips:
        s, e = t, t + c["_dur"]
        for g in c.get("text", []):
            a, b = s + g.get("at", 0), min(e, s + g.get("at", 0) + g.get("dur", c["_dur"]))
            st = g["style"]
            txt = g["t"]
            if st == "Title":   # slow tracking-in + fade
                txt = r"{\fad(600,700)\fscx112\t(0," + str(int((b - a) * 1000)) + r",\fscx100)\blur1}" + txt
            elif st == "Kicker":
                txt = r"{\fad(500,500)}" + txt
            elif st == "Chapter":  # slide in from the left
                txt = (r"{\fad(250,400)\move(" + f"{int(40*sc)},{H-int(90*sc)},{int(90*sc)},{H-int(90*sc)}" +
                       r",0,350)\an1}" + txt)
            elif st == "ChapterNum":
                txt = r"{\fad(250,400)}" + txt
            elif st == "Note":
                txt = r"{\fad(300,300)}" + txt
            ev.append(f"Dialogue: 2,{ts(a)},{ts(b)},{st},,0,0,0,,{txt}")
        for cap in c.get("captions", []):
            # caption times are given in SOURCE seconds; map into the clip's timeline
            sp = c.get("speed", 1.0)
            a = s + (cap["s"] - c["in"]) / sp
            b = s + (cap["e"] - c["in"]) / sp
            a, b = max(a, s), min(b, e)
            if b - a < 0.3:
                continue
            # pop-in: scale 85% -> 100% in 120 ms
            ev.append(f"Dialogue: 1,{ts(a)},{ts(b)},Cap,,0,0,0,,"
                      r"{\fad(80,120)\fscx85\fscy85\t(0,120,\fscx100\fscy100)}" + cap["t"])
        t = e
    open(path, "w", encoding="utf-8").write(hdr + "\n".join(ev) + "\n")
    return t


def main():
    clips = EDL["clips"]
    files = []
    for i, c in enumerate(clips):
        files.append(render_clip(i, c))
        print(f"clip {i:3d}  {c.get('label','')[:40]:40s} {c['_dur']:6.2f}s", flush=True)
    lst = os.path.join(WORK, "concat.txt")
    open(lst, "w").write("".join(f"file '{f}'\n" for f in files))
    joined = os.path.join(WORK, "joined.mp4")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])
    total = build_ass(clips, os.path.join(WORK, "overlay.ass"))
    print("timeline length", round(total, 2))

    # ---------------------------------------------------------------- music + SFX mix
    # Music cues: {"file","start"(timeline s),"end","gain_db","fade_in","fade_out","offset"}
    # SFX cues:   {"file","at"(timeline s) OR "clip"+"clip_at","gain_db"}
    starts = []; t = 0
    for c in clips:
        starts.append(t); t += c["_dur"]

    def tl(cue, key="at"):
        if "clip" in cue:
            return starts[cue["clip"]] + cue.get("clip_at", 0)
        return cue[key]

    inputs = ["-i", joined]
    n_in = 1
    fparts = []
    mus_labels = []
    for k, m in enumerate(EDL["music"]):
        st = starts[m["clip"]] if "clip" in m else m["start"]
        en = (starts[m["end_clip"]] + clips[m["end_clip"]]["_dur"]) if "end_clip" in m else m["end"]
        d = en - st
        inputs += ["-stream_loop", "-1", "-i", os.path.join(A, m["file"])]
        idx = n_in; n_in += 1
        fparts.append(f"[{idx}:a]atrim=start={m.get('offset',0)}:duration={d:.3f},asetpts=PTS-STARTPTS,"
                      f"afade=t=in:st=0:d={m.get('fade_in',1.5)},afade=t=out:st={d-m.get('fade_out',2):.3f}:d={m.get('fade_out',2)},"
                      f"volume={m.get('gain_db',-14)}dB,aresample=48000,adelay={int(st*1000)}|{int(st*1000)}[m{k}]")
        mus_labels.append(f"[m{k}]")
    sfx_labels = []
    for k, s in enumerate(EDL["sfx"]):
        at = tl(s)
        inputs += ["-i", os.path.join(A, s["file"])]
        idx = n_in; n_in += 1
        fparts.append(f"[{idx}:a]volume={s.get('gain_db',-8)}dB,aresample=48000,adelay={int(max(at,0)*1000)}|{int(max(at,0)*1000)}[s{k}]")
        sfx_labels.append(f"[s{k}]")
    # dialogue is the sidechain key that ducks music under speech; use the enhanced voice
    # track when the EDL provides one, else the per-clip audio baked into joined.mp4
    dsrc = "[0:a]"
    if EDL.get("dialogue_audio"):
        inputs += ["-i", build_dialogue(clips)]
        dsrc = f"[{n_in}:a]"; n_in += 1
        print("dialogue: enhanced voice track built", flush=True)
    fparts.append(f"{dsrc}asplit=2[dlg][key]")
    fparts.append("".join(mus_labels) + f"amix=inputs={len(mus_labels)}:normalize=0:duration=longest[mus]")
    fparts.append("[mus][key]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400:makeup=1[musd]")
    fparts.append("[dlg][musd]" + "".join(sfx_labels) +
                  f"amix=inputs={2+len(sfx_labels)}:normalize=0:duration=first,"
                  "alimiter=limit=0.95,loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    ass = os.path.join(WORK, "overlay.ass").replace(":", r"\:")
    fontsdir = os.path.join(A, "fonts")
    vf = f"subtitles=filename='{ass}':fontsdir='{fontsdir}'"
    if EDL.get("grain", True):
        vf = "noise=alls=3:allf=t+u," + vf  # light grain; bitrate is capped below
    out = os.path.join(P, "06_final", "Preview.mp4" if PREVIEW else "Final_Edited_Video.mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error"] + inputs + [
        "-filter_complex", ";".join(fparts) + f";[0:v]{vf}[vout]",
        "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "veryfast" if PREVIEW else "medium", "-crf", "20" if PREVIEW else "19", "-maxrate", "12M", "-bufsize", "24M",
        "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", str(FPS * 2),
        "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-movflags", "+faststart", out]
    run(cmd)
    print("wrote", out)


if __name__ == "__main__":
    main()
