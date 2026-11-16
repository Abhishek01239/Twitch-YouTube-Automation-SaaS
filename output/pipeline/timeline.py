"""Shared timeline for the Vice City cinematic (beat-synced at 140 BPM)."""
BPM = 140
BEAT = 60.0 / BPM          # 0.428571 s
BAR = 4 * BEAT
FPS = 30
W, H = 1080, 1920
DURATION = 38.0

def b(n):  # beats -> seconds
    return n * BEAT

# Section boundaries (seconds)
DROP = b(4)        # 1.714  bass drop / title
CAR = b(12)        # 5.143
CLUB = b(28)       # 12.0
CHASE = b(48)      # 20.571
ENDING = b(72)     # 30.857
ENDCARD = b(80)    # 34.286

# Shot list: (start_beat, end_beat, image, move, fx)
# move: dict(z=(z0,z1), x=(x0,x1), y=(y0,y1), r=(r0,r1), ease)
#   z = zoom factor relative to "cover" fit, x/y = crop centre in normalised source coords
# fx: set of effect tags
SHOTS = [
    (0, 2,  "I_11", dict(z=(1.25, 1.10), x=(.5, .5), y=(.55, .52), r=(-2, 1), ease="out"), {"police", "rain", "shake2"}),
    (2, 4,  "C_11", dict(z=(1.05, 1.30), x=(.5, .5), y=(.55, .58), r=(0, 0), ease="in"), {"rain", "streaks", "shake1"}),
    (4, 8,  "A_99", dict(z=(1.30, 1.12), x=(.45, .55), y=(.45, .5), r=(1.5, 0), ease="out"), {"sun"}),
    (8, 12, "A_7",  dict(z=(1.08, 1.22), x=(.48, .55), y=(.55, .5), r=(0, -1), ease="inout"), {"sun"}),
    (12, 16, "B_42", dict(z=(1.0, 1.06), x=(.30, .70), y=(.55, .55), r=(0, 0), ease="lin"), {"streaks", "shake1"}),
    (16, 20, "C_42", dict(z=(1.05, 1.35), x=(.5, .5), y=(.6, .62), r=(0, 0), ease="in"), {"streaks", "shake1"}),
    (20, 24, "D_42", dict(z=(1.15, 1.20), x=(.42, .58), y=(.62, .62), r=(-1, 1), ease="lin"), {"streaks", "shake2"}),
    (24, 26, "D_11", dict(z=(1.10, 1.25), x=(.55, .45), y=(.45, .45), r=(0, 0), ease="lin"), {"streaks", "shake2"}),
    (26, 28, "C_11", dict(z=(1.15, 1.45), x=(.5, .5), y=(.55, .55), r=(0, 2), ease="in"), {"rain", "streaks", "shake2"}),
    (28, 34, "E_11", dict(z=(1.05, 1.22), x=(.5, .5), y=(.45, .40), r=(0, 0), ease="inout"), {"club", "walk"}),
    (34, 38, "F_42", dict(z=(1.25, 1.10), x=(.55, .5), y=(.40, .40), r=(0, 0), ease="out"), {"club"}),
    (38, 40, "E_42", dict(z=(1.10, 1.25), x=(.5, .5), y=(.45, .40), r=(0, 0), ease="lin"), {"club", "walk"}),
    (40, 44, "F_11", dict(z=(1.10, 1.30), x=(.45, .5), y=(.40, .38), r=(0, 0), ease="inout"), {"club"}),
    (44, 48, "E_11", dict(z=(1.55, 1.80), x=(.5, .5), y=(.30, .30), r=(0, 0), ease="in"), {"club", "strobe"}),
    (48, 50, "G_99", dict(z=(1.10, 1.30), x=(.5, .5), y=(.6, .62), r=(0, 0), ease="in"), {"police", "streaks", "shake2", "wanted"}),
    (50, 52, "L_99", dict(z=(1.10, 1.25), x=(.5, .5), y=(.6, .6), r=(-2, 2), ease="lin"), {"police", "streaks", "shake2", "wanted"}),
    (52, 54, "I_11", dict(z=(1.35, 1.15), x=(.45, .5), y=(.5, .5), r=(2, -1), ease="out"), {"police", "rain", "shake3", "wanted"}),
    (54, 56, "H_7",  dict(z=(1.10, 1.25), x=(.5, .5), y=(.6, .58), r=(0, 0), ease="in"), {"police", "streaks", "shake2", "wanted"}),
    (56, 60, "M_99", dict(z=(1.20, 1.10), x=(.62, .45), y=(.62, .6), r=(-3, 2), ease="out"), {"police", "smoke", "shake3", "wanted"}),
    (60, 62, "G_7",  dict(z=(1.10, 1.25), x=(.5, .55), y=(.55, .55), r=(0, -2), ease="lin"), {"police", "streaks", "shake2", "wanted"}),
    (62, 64, "M_7",  dict(z=(1.25, 1.10), x=(.4, .6), y=(.6, .6), r=(3, -2), ease="out"), {"police", "smoke", "shake3", "wanted"}),
    (64, 66, "D_42", dict(z=(1.30, 1.40), x=(.35, .60), y=(.62, .62), r=(0, 0), ease="lin"), {"police", "streaks", "shake3", "wanted"}),
    (66, 68, "L_99", dict(z=(1.40, 1.15), x=(.5, .5), y=(.55, .6), r=(0, 0), ease="out"), {"police", "streaks", "shake3", "wanted"}),
    (68, 70, "I_11", dict(z=(1.10, 1.45), x=(.5, .5), y=(.5, .55), r=(0, 3), ease="in"), {"police", "rain", "shake3", "wanted"}),
    (70, 72, "C_11", dict(z=(1.10, 1.60), x=(.5, .5), y=(.55, .55), r=(0, 0), ease="in"), {"police", "rain", "streaks", "shake3", "wanted"}),
    (72, 80, "J_11", dict(z=(1.30, 1.05), x=(.5, .5), y=(.40, .55), r=(1.5, 0), ease="out"), {"twinkle"}),
    (80, 88.7, "K_42", dict(z=(1.02, 1.25), x=(.5, .5), y=(.55, .45), r=(0, 0), ease="inout"), {"twinkle", "police_far"}),
]

# Cuts that get a big transition (flash + zoom blur)
BIG_CUTS = [b(4), b(12), b(28), b(48), b(72)]
SOFT_CUTS = [b(80)]  # dissolve
