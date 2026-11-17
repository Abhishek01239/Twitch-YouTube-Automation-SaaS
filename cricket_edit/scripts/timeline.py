"""Edit decision list for 'Sunny Sir vs KD Sir' — shared by video + audio renderers.

Music is 120 BPM, so one beat = 0.5 s. Every cut lands on that grid and every
bat impact lands exactly on a beat.

Segment fields
  src    (in, out) seconds in the source clip
  speed  playback speed (0.5 = slow motion, >1 = fast forward)
  zoom   keyframes [(t_rel_out_seconds, zoom, cx, cy)], smooth-interpolated
  bars   cinematic letterbox bars (slow-motion beats)
  bg     blurred / darkened plate behind a title card (original audio muted)
  audio  gain applied to the original audio of this segment
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source", "source_original.mp4")
W, H, FPS = 1920, 1080, 60
BEAT = 0.5

# Source seconds 36.5-62 carry a thin baked-in black border -> keep >= 1.035 zoom.
B = 1.035

SEGMENTS = [
    # ---------- COLD OPEN (hook) ----------
    dict(name="hook_windup", src=(72.43, 72.93), speed=1.0, zoom=[(0, 1.04, .35, .6), (.5, 1.08, .35, .62)]),
    dict(name="hook_six_slo", src=(72.93, 73.43), speed=0.5, bars=True,
         zoom=[(0, 1.08, .35, .62), (1.0, 1.2, .3, .62)]),
    dict(name="hook_grin", src=(46.3, 46.8), speed=1.0, zoom=[(0, 1.12, .45, .6), (.5, 1.16, .45, .6)]),
    dict(name="hook_debate", src=(80.3, 80.8), speed=1.0, zoom=[(0, 1.0, .5, .5), (.5, 1.05, .5, .45)]),
    dict(name="hook_arms", src=(87.3, 88.3), speed=2 / 3, zoom=[(0, 1.0, .45, .5), (1.5, 1.1, .45, .5)]),
    # ---------- TITLE ----------
    dict(name="title_bg", src=(28.5, 30.5), speed=0.5, bg=True, audio=0.0,
         zoom=[(0, 1.05, .5, .5), (4, 1.15, .5, .5)]),
    # ---------- ROUND 1 : first batter ----------
    dict(name="b1_runup", src=(2.43, 3.93), speed=1.0, zoom=[(0, 1.0, .5, .55), (1.5, 1.06, .52, .6)]),
    dict(name="b1_hit_slo", src=(3.93, 4.43), speed=0.5, bars=True,
         zoom=[(0, 1.06, .52, .6), (1.0, 1.2, .5, .55)]),
    dict(name="b1_four", src=(4.43, 6.93), speed=1.25, zoom=[(0, 1.0, .5, .5), (2, 1.04, .5, .5)]),
    dict(name="b1_look", src=(9.2, 10.7), speed=1.0, zoom=[(0, 1.02, .6, .6), (1.5, 1.12, .62, .6)]),
    dict(name="b2_runup", src=(16.83, 18.33), speed=1.0, zoom=[(0, 1.0, .6, .55), (1.5, 1.06, .6, .6)]),
    dict(name="b2_hit_slo", src=(18.33, 18.83), speed=0.5, bars=True,
         zoom=[(0, 1.06, .6, .6), (1.0, 1.2, .6, .55)]),
    dict(name="b2_four", src=(18.83, 21.83), speed=1.5, zoom=[(0, 1.0, .5, .5), (2, 1.04, .5, .5)]),
    # ---------- CHANGE OVER ----------
    dict(name="changeover_ff", src=(23.5, 27.5), speed=4.0, audio=0.0, zoom=[(0, 1.0, .5, .5)]),
    dict(name="walk_in", src=(28.5, 32.5), speed=2.0, audio=0.6, zoom=[(0, 1.0, .4, .55), (2, 1.05, .4, .6)]),
    dict(name="pose", src=(32.5, 34.5), speed=1.0, zoom=[(0, 1.05, .4, .6), (2, 1.14, .42, .55)]),
    # ---------- ROUND 2 : second batter ----------
    dict(name="stance", src=(37.0, 39.0), speed=1.0, zoom=[(0, B, .45, .55), (2, 1.1, .45, .6)]),
    dict(name="pitch_walker", src=(40.0, 43.5), speed=1.75, audio=0.6, zoom=[(0, B, .4, .6), (2, 1.08, .35, .65)]),
    dict(name="nb_delivery", src=(43.9, 44.9), speed=1.0, zoom=[(0, B, .5, .55), (1, 1.07, .5, .55)]),
    dict(name="nb_reaction", src=(44.9, 48.4), speed=1.0,
         zoom=[(0, 1.07, .5, .55), (1.0, 1.05, .45, .6), (1.6, 1.16, .45, .62), (2.6, 1.16, .55, .65), (3.5, 1.06, .6, .6)]),
    dict(name="dot_setup", src=(56.1, 57.6), speed=1.0, zoom=[(0, B, .5, .55), (1.5, 1.08, .5, .6)]),
    dict(name="dot_swing_slo", src=(57.6, 58.1), speed=0.5, bars=True,
         zoom=[(0, 1.08, .5, .6), (1.0, 1.2, .48, .55)]),
    dict(name="dot_result", src=(58.1, 59.6), speed=1.0, zoom=[(0, B, .5, .5), (1.5, 1.06, .5, .5)]),
    dict(name="dot_react", src=(60.0, 61.5), speed=1.0, zoom=[(0, 1.05, .5, .55), (1.5, 1.14, .48, .5)]),
    # ---------- THE SIX ----------
    dict(name="six_setup", src=(70.93, 72.93), speed=1.0, zoom=[(0, 1.0, .35, .6), (2, 1.08, .35, .62)]),
    dict(name="six_hit_slo", src=(72.93, 73.68), speed=0.5, bars=True,
         zoom=[(0, 1.08, .35, .62), (1.5, 1.22, .3, .62)]),
    dict(name="six_flight", src=(73.68, 75.43), speed=0.875, zoom=[(0, 1.0, .5, .5), (2, 1.04, .5, .5)]),
    dict(name="six_grin", src=(75.43, 77.93), speed=1.0, zoom=[(0, 1.0, .4, .5), (2.5, 1.08, .4, .5)]),
    # ---------- AFTERMATH ----------
    dict(name="debate_1", src=(78.0, 82.5), speed=1.0, zoom=[(0, 1.0, .5, .5), (4.5, 1.05, .5, .45)]),
    dict(name="debate_2", src=(82.5, 86.5), speed=1.0, zoom=[(0, 1.0, .5, .5), (4, 1.04, .5, .45)]),
    dict(name="turn", src=(86.5, 87.0), speed=1.0, zoom=[(0, 1.0, .5, .5)]),
    dict(name="arms_up_slo", src=(87.0, 88.25), speed=0.5, bars=True,
         zoom=[(0, 1.0, .45, .5), (2.5, 1.14, .45, .45)]),
    # ---------- END CARD ----------
    dict(name="end_bg", src=(12.0, 14.0), speed=0.5, bg=True, audio=0.0,
         zoom=[(0, 1.05, .5, .5), (4, 1.15, .5, .5)]),
]

t = 0.0
for s in SEGMENTS:
    s["dur"] = (s["src"][1] - s["src"][0]) / s["speed"]
    s["t0"] = t
    t += s["dur"]
    s["t1"] = t
TOTAL = t


def T(name):
    for s in SEGMENTS:
        if s["name"] == name:
            return s["t0"]
    raise KeyError(name)


# Cuts that get a white flash + zoom punch (section changes / big hits)
FLASHES = [T("hook_six_slo"), T("title_bg"), T("title_bg") + 1.0, T("b1_runup"), T("b1_hit_slo"), T("b2_hit_slo"),
           T("nb_reaction"), T("six_hit_slo"), T("six_flight"), T("end_bg")]
PUNCHES = [T("hook_grin"), T("hook_debate"), T("hook_arms"), T("b1_four"), T("b2_four"), T("walk_in"),
           T("stance"), T("dot_result"), T("six_flight"), T("debate_1")]
SHAKES = [(T("hook_six_slo"), .35), (T("title_bg") + 1.0, .3), (T("b1_hit_slo"), .3), (T("b2_hit_slo"), .3),
          (T("nb_reaction"), .45), (T("six_hit_slo"), .45)]

if __name__ == "__main__":
    for s in SEGMENTS:
        print(f"{s['t0']:6.2f} -> {s['t1']:6.2f}  {s['name']:16s} src {s['src']}  x{s['speed']:.2f}")
    print("TOTAL", TOTAL)
