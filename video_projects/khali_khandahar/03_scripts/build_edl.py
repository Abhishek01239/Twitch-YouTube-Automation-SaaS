"""Builds 03_scripts/edl.json — the edit decision list for the final cut.

Every in/out point is chosen from inspected footage (contact sheets in 02_analysis/sheets)
and then *snapped* to the quietest half-second within +/-SNAP s using the loudness profile,
so cuts land in speech gaps instead of mid-word.
Times are SOURCE seconds in 01_source/original_cloudinary_360p.mp4.
"""
import json, os, sys

P = os.path.abspath(sys.argv[1])
loud = {}
for line in open(os.path.join(P, "02_analysis", "loudness_halfsec.tsv")):
    t, d = line.split()
    loud[float(t)] = float(d)
SNAP = 0.75


def snap(t, window=SNAP):
    if t is None:
        return None
    cands = [k for k in loud if abs(k - t) <= window]
    if not cands:
        return t
    best = min(cands, key=lambda k: (loud[k], abs(k - t)))
    return best + 0.25  # centre of the quiet half-second


clips = []
music = []
sfx = []


def add(label, a, b, grade, snap_ends=True, **kw):
    if snap_ends:
        a, b = snap(a), snap(b)
    c = dict(label=label, **{"in": round(a, 3), "out": round(b, 3)}, grade=grade, **kw)
    clips.append(c)
    return len(clips) - 1


def card(label, secs, text):
    clips.append({"label": label, "in": 0, "out": secs, "card": secs, "text": text})
    return len(clips) - 1


def chapter(num, name):
    return [{"style": "ChapterNum", "t": f"CHAPTER {num:02d}", "at": 0.4, "dur": 3.6},
            {"style": "Chapter", "t": name, "at": 0.4, "dur": 3.6}]


def cap(s, e, t):
    return {"s": s, "e": e, "t": t}


# ---------------------------------------------------------------- 0. disclaimer (creator's own card)
add("disclaimer", 0.0, 3.0, "none", snap_ends=False, fade_out=0.3)

# ---------------------------------------------------------------- 1. cold open: tease of the night
c1 = add("cold: running in the dark", 772.0, 774.5, "night", snap_ends=False, zoom=0.07, fade_in=0.15)
c2 = add("cold: friend found crouched", 790.0, 793.0, "night", snap_ends=False, zoom=0.10)
c3 = add("cold: panic", 800.0, 802.3, "night", snap_ends=False, zoom=-0.06)
c4 = add("cold: dropped phone (slow-mo)", 991.4, 993.2, "night", snap_ends=False, speed=0.5, slowmo=True,
         fade_out=0.6, zoom=0.05)
for c in (c1, c2, c3):
    sfx.append({"file": "sfx/sub_hit.wav", "clip": c, "clip_at": 0.0, "gain_db": -6})
sfx.append({"file": "sfx/static_glitch.wav", "clip": c4, "clip_at": 0.0, "gain_db": -10})
sfx.append({"file": "sfx/riser_4s.wav", "clip": c4, "clip_at": -0.4, "gain_db": -9})
# creator's own logline (from the video title); 2nd line fades in later, same layout so no overlap
k = card("hook card", 4.5, [
    {"style": "Kicker", "t": r"They call it Khali Khandahar\N{\alpha&HFF&}because no living soul remains.", "at": 0.3, "dur": 3.9},
    {"style": "Kicker", "t": r"{\alpha&HFF&}They call it Khali Khandahar\N{\alpha&H00&}because no living soul remains.", "at": 1.6, "dur": 2.6}])
sfx.append({"file": "sfx/impact_braam.wav", "clip": k, "clip_at": 0.0, "gain_db": -5})

# ---------------------------------------------------------------- 2. original opening titles & credits
t0 = add("opening credits + title", 3.0, 22.6, "none", snap_ends=False, fade_in=0.4, orig_gain_db=-3)
sfx.append({"file": "sfx/reverse_swell.wav", "clip": t0, "clip_at": 17.0 - 2.5 + 0.0, "gain_db": -9})
sfx.append({"file": "sfx/impact_braam.wav", "clip": t0, "clip_at": 17.0, "gain_db": -8})

# ---------------------------------------------------------------- 3. CH1 — the channel (day)
d1 = add("temple vlog: sky", 23.0, 27.0, "day", snap_ends=False, speed=1.25, fade_in=0.3,
         text=chapter(1, "THE CHANNEL"))
sfx.append({"file": "sfx/whoosh.wav", "clip": d1, "clip_at": 0.0, "gain_db": -12})
add("temple vlog: intro to camera", 27.0, 41.6, "day", zoom=0.04,
    captions=[cap(35.6, 37.8, "Let's see what's inside the temple.")])
add("walk around the rocks (ramp)", 61.3, 68.9, "day", snap_ends=False, speed=1.6, orig_gain_db=-6)
add("heading home (ramp)", 70.4, 77.6, "day", snap_ends=False, speed=1.6, orig_gain_db=-6)

# ---------------------------------------------------------------- 4. the room — no views
add("laptop set-up (ramp)", 78.0, 86.0, "room", snap_ends=False, speed=1.6)
add("checking the channel", 103.8, 125.0, "room", zoom=0.05)
add("friends arrive / views talk", 129.0, 147.8, "room", zoom=-0.04)
add("close-up reactions", 235.5, 246.0, "room", zoom=0.04)
add("the plan: you three go", 252.0, 262.0, "room", zoom=-0.04)
add("the plan continues", 265.0, 279.0, "room", zoom=0.05)
r_end = add("leaving the room", 304.0, 311.0, "room", fade_out=0.5)
sfx.append({"file": "sfx/whoosh.wav", "clip": r_end, "clip_at": 6.0, "gain_db": -10})

# ---------------------------------------------------------------- 5. CH2 — the road (dusk, music-driven)
w0 = add("wide walk (ramp)", 316.0, 331.0, "dusk", snap_ends=False, speed=1.6, orig_gain_db=-10, fade_in=0.4,
         text=chapter(2, "THE ROAD"))
add("on the road", 332.0, 341.0, "dusk", speed=1.25, orig_gain_db=-6)
add("road walk (ramp)", 343.0, 355.8, "dusk", snap_ends=False, speed=1.6, orig_gain_db=-10)
add("feet on gravel (slow-mo)", 356.2, 358.6, "dusk", snap_ends=False, speed=0.6, slowmo=True, mute=True)
add("walking talk", 362.0, 375.0, "dusk", zoom=0.04)
add("is this the house?", 384.8, 400.9, "dusk", zoom=0.05,
    captions=[cap(385.6, 387.8, "Look — is this the house we were talking about?"),
              cap(387.9, 389.3, "Yeah, that's the one."),
              cap(390.2, 392.7, "I'll start filming.")])
w_man = add("the old man", 402.8, 432.6, "dusk", zoom=-0.04,
            captions=[cap(406.1, 407.4, "Hey, dada — what happened?"),
                      cap(411.2, 413.0, "Kids, what are you doing here?"),
                      cap(413.2, 414.6, "We just want to make a video.")])
sfx.append({"file": "sfx/heartbeat.wav", "clip": w_man, "clip_at": 3.0, "gain_db": -12})
rev = add("the building reveal", 474.0, 490.0, "dusk", zoom=0.10)
sfx.append({"file": "sfx/reverse_swell.wav", "clip": rev, "clip_at": 0.0, "gain_db": -10})
sfx.append({"file": "sfx/sub_hit.wav", "clip": rev, "clip_at": 2.5, "gain_db": -8})
add("approach (ramp)", 493.0, 505.0, "dusk", snap_ends=False, speed=1.5, orig_gain_db=-6, fade_out=0.6)

# ---------------------------------------------------------------- 6. CH3 — inside (night)
n0 = add("entering the ruins", 512.8, 540.0, "night", fade_in=0.6, text=chapter(3, "INSIDE"))
sfx.append({"file": "sfx/whoosh.wav", "clip": n0, "clip_at": 0.0, "gain_db": -12})
add("the staircase", 550.0, 575.0, "night", zoom=0.05)
add("upstairs", 590.0, 602.4, "night", zoom=-0.04)
add("searching the walls", 603.0, 616.0, "night", zoom=0.05)
add("separating", 655.0, 670.0, "night", zoom=0.05)
add("the window", 687.4, 708.6, "night", zoom=0.04)
add("alone", 711.0, 735.0, "night", zoom=0.06)
sfx.append({"file": "sfx/heartbeat.wav", "clip": len(clips) - 1, "clip_at": 10.0, "gain_db": -10})
s0 = add("something is wrong", 735.0, 760.3, "night", zoom=-0.05)
add("the run", 760.3, 789.6, "night", snap_ends=False,
    captions=[cap(774.1, 774.7, "Sumant?"), cap(774.8, 776.0, "You go this way, okay?"),
              cap(782.9, 784.0, "Is Sumant here?"), cap(784.1, 785.6, "Hey, he's over here!")])
add("found in the corner", 789.6, 830.0, "night", snap_ends=False, zoom=0.04,
    captions=[cap(804.6, 806.5, "I don't know... he was right behind me."),
              cap(807.9, 810.9, "I'll go upstairs. Don't leave him alone, okay?")])
add("after", 848.0, 862.0, "night", zoom=0.05)
add("the escape begins", 907.8, 930.3, "night", snap_ends=False,
    text=chapter(4, "THE WAY OUT"))
add("outside, in the dark", 930.3, 961.0, "night", snap_ends=False, zoom=0.03)
add("we have to take him", 966.5, 978.0, "night", snap_ends=False, zoom=0.04)
cl = add("climax", 978.0, 1038.6, "night", snap_ends=False,
         captions=[cap(981.9, 982.8, "What happened?"), cap(987.2, 988.8, "Hey, what happened? Ansh? Ansh?"),
                   cap(1032.0, 1032.6, "Ansh?")])
sfx.append({"file": "sfx/sub_hit.wav", "clip": cl, "clip_at": 13.3, "gain_db": -6})
end = add("the last shot", 1038.6, 1049.6, "night", snap_ends=False, fade_out=0.8)
sfx.append({"file": "sfx/impact_braam.wav", "clip": end, "clip_at": 3.9, "gain_db": -6})
card("end card", 5.0, [{"style": "Kicker", "t": "A film by Team Boys", "at": 0.4, "dur": 4.2}])

# ---------------------------------------------------------------- music cues (all original, synthesized)
idx = {c["label"]: i for i, c in enumerate(clips)}
music += [
    {"file": "music/bed_climax_heartbeat_112bpm.wav", "clip": idx["cold: running in the dark"],
     "end_clip": idx["cold: dropped phone (slow-mo)"], "gain_db": -16, "fade_in": 0.3, "fade_out": 1.0},
    {"file": "music/bed_dark_ambient_loop.wav", "clip": idx["hook card"],
     "end_clip": idx["opening credits + title"], "gain_db": -18, "fade_in": 1.0, "fade_out": 2.0},
    {"file": "music/bed_dark_ambient_loop.wav", "clip": idx["checking the channel"],
     "end_clip": idx["leaving the room"], "gain_db": -26, "fade_in": 3.0, "fade_out": 2.0, "offset": 10},
    {"file": "music/bed_dusk_pulse_84bpm.wav", "clip": idx["wide walk (ramp)"],
     "end_clip": idx["approach (ramp)"], "gain_db": -17, "fade_in": 1.0, "fade_out": 2.0},
    {"file": "music/bed_dark_ambient_loop.wav", "clip": idx["entering the ruins"],
     "end_clip": idx["something is wrong"], "gain_db": -19, "fade_in": 3.0, "fade_out": 3.0},
    {"file": "music/bed_climax_heartbeat_112bpm.wav", "clip": idx["the escape begins"],
     "end_clip": idx["climax"], "gain_db": -20, "fade_in": 4.0, "fade_out": 3.0},
    {"file": "music/bed_dark_ambient_loop.wav", "clip": idx["the last shot"],
     "end_clip": idx["end card"], "gain_db": -16, "fade_in": 0.5, "fade_out": 2.5, "offset": 30},
]

edl = {"source": "01_source/original_cloudinary_360p.mp4",
       "fonts": {"title": "Inter Display Black", "ui": "Inter Display SemiBold", "caption": "Inter ExtraBold"},
       "grain": True, "clips": clips, "music": music, "sfx": sfx}
json.dump(edl, open(os.path.join(P, "03_scripts", "edl.json"), "w"), indent=1, ensure_ascii=False)
tot = sum(c.get("card") or (c["out"] - c["in"]) / c.get("speed", 1.0) for c in clips)
print(f"{len(clips)} clips, est. runtime {tot/60:.1f} min")
