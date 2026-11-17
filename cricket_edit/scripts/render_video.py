"""Video renderer: cuts, speed ramps, grade, zooms, flashes, shakes and broadcast graphics.

ffmpeg decodes each segment (speed change + colour grade + upscale) into raw frames,
Python composites zoom / effects / graphics, and ffmpeg encodes the result.
Usage: render_video.py OUT.mp4 [t_start t_end]   (optional range = fast preview)
"""
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from timeline import FLASHES, FPS, H, PUNCHES, ROOT, SEGMENTS, SHAKES, SRC, T, TOTAL, W

ASSETS = os.path.join(ROOT, "assets")
ANTON = os.path.join(ASSETS, "anton-latin-400-normal.woff")
BEBAS = os.path.join(ASSETS, "bebas-neue-latin-400-normal.woff")

GOLD, RED, WHITE, NAVY, INK = (255, 205, 40), (226, 30, 45), (255, 255, 255), (10, 16, 34), (8, 10, 18)

# Colour grade: lift the haze, add contrast, gently warm the cyan cast, mild sharpen.
GRADE = ("scale=1920:1080:flags=lanczos:in_color_matrix=bt709,format=rgb24,"
         "eq=contrast=1.10:brightness=-0.015:saturation=1.12:gamma=0.96,"
         "colorbalance=rm=0.04:gm=-0.01:bm=-0.05:rh=0.03:bh=-0.03:rs=0.01:bs=0.02,"
         "curves=all='0/0 0.25/0.215 0.5/0.5 0.75/0.79 1/1',"
         "unsharp=5:5:0.6:5:5:0.0")
BG_EXTRA = ",gblur=sigma=14,eq=brightness=-0.22:saturation=0.75"


# ------------------------------------------------------------------ helpers
def font(path, size):
    return ImageFont.truetype(path, size)


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def shear(img, k=0.16):
    """Italic slant for a sporty look."""
    w, h = img.size
    pad = int(abs(k) * h) + 2
    out = Image.new("RGBA", (w + pad, h), (0, 0, 0, 0))
    out.paste(img, (pad if k > 0 else 0, 0))
    return out.transform(out.size, Image.AFFINE, (1, k, -k * h if k > 0 else 0, 0, 1, 0), Image.BICUBIC)


def text_img(txt, path, size, fill=WHITE, stroke=0, stroke_fill=INK, shadow=8, tracking=0):
    f = font(path, size)
    if tracking:
        widths = [f.getlength(c) for c in txt]
        tw = int(sum(widths) + tracking * (len(txt) - 1))
    else:
        tw = int(f.getlength(txt))
    asc, desc = f.getmetrics()
    pad = stroke + shadow + 12
    img = Image.new("RGBA", (tw + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))

    def draw(d, off, col, st, stf):
        x = pad + off
        if tracking:
            for c, cw in zip(txt, widths):
                d.text((x, pad + off), c, font=f, fill=col, stroke_width=st, stroke_fill=stf)
                x += cw + tracking
        else:
            d.text((x, pad + off), txt, font=f, fill=col, stroke_width=st, stroke_fill=stf)

    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw(ImageDraw.Draw(sh), shadow * 0.6, (0, 0, 0, 170), stroke, (0, 0, 0, 170))
        img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(shadow * 0.6)))
    draw(ImageDraw.Draw(img), 0, fill, stroke, stroke_fill)
    return img.crop(img.getbbox())


def plate(w, h, color, skew=28, alpha=255):
    img = Image.new("RGBA", (w + skew, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).polygon([(skew, 0), (w + skew, 0), (w, h), (0, h)], fill=color + (alpha,))
    return img


def stack(*rows, gap=6, align="left"):
    w = max(r.width for r in rows)
    h = sum(r.height for r in rows) + gap * (len(rows) - 1)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    y = 0
    for r in rows:
        x = 0 if align == "left" else (w - r.width) // 2
        out.alpha_composite(r, (x, y))
        y += r.height + gap
    return out


def with_shadow(img, blur=14, off=8, alpha=150):
    pad = blur * 2 + off
    out = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
    a = img.getchannel("A").point(lambda v: v * alpha // 255)
    sh = Image.new("RGBA", img.size, (0, 0, 0, 255))
    sh.putalpha(a)
    out.alpha_composite(sh, (pad + off, pad + off))
    out = out.filter(ImageFilter.GaussianBlur(blur))
    out.alpha_composite(img, (pad, pad))
    return out


# ------------------------------------------------------------------ sprite builders
def lower_third(title, sub):
    t = text_img(title, ANTON, 78, WHITE, shadow=0)
    s = text_img(sub, BEBAS, 44, NAVY, shadow=0, tracking=2)
    w = max(t.width + 110, s.width + 120)
    top = plate(w, 112, NAVY, alpha=235)
    ImageDraw.Draw(top).polygon([(28, 0), (46, 0), (18, 112), (0, 112)], fill=GOLD + (255,))
    top.alpha_composite(t, (64, (112 - t.height) // 2 + 2))
    bot = plate(s.width + 90, 58, GOLD)
    bot.alpha_composite(s, (48, (58 - s.height) // 2 + 1))
    out = Image.new("RGBA", (top.width + 10, 112 + 58), (0, 0, 0, 0))
    out.alpha_composite(top, (0, 0))
    out.alpha_composite(bot, (0, 112))
    return with_shadow(out)


def caption(txt):
    """Commentary-style quip: white on a dark slanted plate with a gold tick."""
    t = text_img(txt, BEBAS, 62, WHITE, shadow=0, tracking=2)
    p = plate(t.width + 120, 92, INK, alpha=215)
    ImageDraw.Draw(p).polygon([(28, 0), (40, 0), (12, 92), (0, 92)], fill=GOLD + (255,))
    p.alpha_composite(t, (66, (92 - t.height) // 2 + 2))
    return with_shadow(p, blur=10, off=5)


def stamp(txt, sub=None, color=GOLD, size=230):
    t = shear(text_img(txt, ANTON, size, color, stroke=10, stroke_fill=INK, shadow=14), 0.14)
    if not sub:
        return t
    s = text_img(sub, BEBAS, 58, NAVY, shadow=0, tracking=3)
    p = plate(s.width + 80, 74, WHITE)
    p.alpha_composite(s, (42, (74 - s.height) // 2 + 2))
    return stack(t, with_shadow(p, blur=8, off=4), gap=-22, align="center")


def bug():
    a = text_img("SUNNY SIR", BEBAS, 40, WHITE, shadow=0, tracking=2)
    v = text_img("VS", ANTON, 30, NAVY, shadow=0)
    b = text_img("KD SIR", BEBAS, 40, WHITE, shadow=0, tracking=2)
    w = a.width + b.width + 150
    p = plate(w, 58, NAVY, skew=16, alpha=225)
    d = ImageDraw.Draw(p)
    x = 30
    p.alpha_composite(a, (x, (58 - a.height) // 2 + 1))
    x += a.width + 18
    d.polygon([(x + 12, 6), (x + 62, 6), (x + 50, 52), (x, 52)], fill=GOLD + (255,))
    p.alpha_composite(v, (x + 31 - v.width // 2, (58 - v.height) // 2 + 1))
    x += 62 + 18
    p.alpha_composite(b, (x, (58 - b.height) // 2 + 1))
    return with_shadow(p, blur=8, off=4, alpha=120)


def ff_badge(txt):
    t = text_img(txt, ANTON, 44, NAVY, shadow=0)
    p = plate(t.width + 70, 66, GOLD, skew=18)
    p.alpha_composite(t, (40, (66 - t.height) // 2 + 1))
    return with_shadow(p, blur=8, off=4)


def no_ball_band():
    band = Image.new("RGBA", (W, 250), RED + (240,))
    d = ImageDraw.Draw(band)
    for x in range(-300, W + 300, 70):  # hazard stripes top & bottom
        d.polygon([(x, 0), (x + 35, 0), (x + 20, 22), (x - 15, 22)], fill=GOLD + (255,))
        d.polygon([(x, 228), (x + 35, 228), (x + 20, 250), (x - 15, 250)], fill=GOLD + (255,))
    d.rectangle([0, 22, W, 26], fill=INK + (255,))
    d.rectangle([0, 224, W, 228], fill=INK + (255,))
    t = shear(text_img("NO BALL!", ANTON, 170, WHITE, stroke=6, stroke_fill=INK, shadow=10), 0.14)
    band.alpha_composite(t, (150, (250 - t.height) // 2 + 4))
    s = text_img("ILLEGAL DELIVERY", BEBAS, 60, NAVY, shadow=0, tracking=4)
    p = plate(s.width + 90, 80, WHITE)
    p.alpha_composite(s, (48, (80 - s.height) // 2 + 2))
    band.alpha_composite(p, (150 + t.width + 60, 60))
    s2 = text_img("CAUGHT ON CAMERA", BEBAS, 44, WHITE, shadow=0, tracking=3)
    band.alpha_composite(s2, (150 + t.width + 100, 152))
    return band


def red_alert():
    """Red glow hugging the frame edges for the No Ball alarm."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.minimum(np.minimum(xx, W - 1 - xx) / 260.0, np.minimum(yy, H - 1 - yy) / 200.0)
    a = (np.clip(1 - d, 0, 1) ** 2 * 200).astype(np.uint8)
    img = Image.new("RGBA", (W, H), RED + (255,))
    img.putalpha(Image.fromarray(a))
    return img


def vignette():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / math.sqrt(2)
    a = (np.clip((r - 0.55) / 0.45, 0, 1) ** 2 * 95).astype(np.uint8)
    return Image.fromarray(a)


def title_card():
    a = shear(text_img("SUNNY SIR", ANTON, 250, WHITE, stroke=8, stroke_fill=INK, shadow=16), 0.14)
    b = shear(text_img("KD SIR", ANTON, 250, WHITE, stroke=8, stroke_fill=INK, shadow=16), 0.14)
    v = text_img("VS", ANTON, 150, NAVY, shadow=0)
    vp = plate(250, 190, GOLD, skew=50)
    vp.alpha_composite(v, ((300 - v.width) // 2, (190 - v.height) // 2 + 4))
    vp = with_shadow(vp, blur=18, off=8, alpha=200)
    sub = text_img("THE ULTIMATE CRICKET FACE-OFF", BEBAS, 70, GOLD, shadow=6, tracking=10)
    return a, b, vp, sub


def end_card():
    q = shear(text_img("WHO WON THE RIVALRY?", ANTON, 170, WHITE, stroke=8, stroke_fill=INK, shadow=14), 0.14)
    n = text_img("SUNNY SIR   OR   KD SIR", BEBAS, 110, GOLD, shadow=8, tracking=6)
    s = text_img("COMMENT YOUR WINNER  •  LIKE  •  SUBSCRIBE", BEBAS, 54, NAVY, shadow=0, tracking=3)
    p = plate(s.width + 100, 80, WHITE)
    p.alpha_composite(s, (54, (80 - s.height) // 2 + 2))
    return q, n, with_shadow(p, blur=8, off=4)


# ------------------------------------------------------------------ graphic elements
class El:
    """Sprite with in/out animation. anchor (ax, ay) = centre point on screen."""

    def __init__(self, img, t0, t1, cx, cy, anim="slide", din=0.22, dout=0.18):
        self.img, self.t0, self.t1, self.cx, self.cy, self.anim, self.din, self.dout = img, t0, t1, cx, cy, anim, din, dout

    def draw(self, frame, t):
        if not (self.t0 <= t < self.t1):
            return
        i = ease_out((t - self.t0) / self.din)
        o = ease_out((self.t1 - t) / self.dout)
        a = min(i, o) if self.anim != "slam" else min(min(1, (t - self.t0) / 0.06), o)
        img, dx, dy = self.img, 0, 0
        if self.anim == "slide":
            dx = -int((1 - i) * 140) - int((1 - o) * 80)
        elif self.anim == "slide_r":
            dx = int((1 - i) * 140) + int((1 - o) * 80)
        elif self.anim == "rise":
            dy = int((1 - i) * 50)
        elif self.anim == "slam":
            sc = 1 + 0.9 * (1 - ease_out((t - self.t0) / 0.16))
            sc *= 1 + 0.02 * math.sin((t - self.t0) * 5)  # gentle breathing
            if abs(sc - 1) > 0.004:
                img = img.resize((max(1, int(img.width * sc)), max(1, int(img.height * sc))), Image.BILINEAR)
        elif self.anim == "wipe":
            wv = int(img.width * ease_out((t - self.t0) / 0.25))
            if wv < img.width:
                img = img.crop((0, 0, max(1, wv), img.height))
            paste(frame, img, int(self.cx - self.img.width / 2), int(self.cy - self.img.height / 2), o)
            return
        paste(frame, img, int(self.cx - img.width / 2) + dx, int(self.cy - img.height / 2) + dy, a)


def paste(frame, img, x, y, a=1.0):
    if a <= 0.01:
        return
    m = img.getchannel("A")
    if a < 0.995:
        m = m.point(lambda v: int(v * a))
    frame.paste(img, (x, y), m)


def build_elements():
    E = []
    LT = (0, 905)  # lower-third anchor: left edge x=70

    def lt(title, sub, t0, t1):
        im = lower_third(title, sub)
        E.append(El(im, t0, t1, 60 + im.width / 2, 880, "slide"))

    def cap(txt, t0, t1):
        E.append(El(caption(txt), t0, t1, W / 2, 955, "rise"))

    def st(txt, sub, t0, t1, color=GOLD, size=230, cy=790):
        E.append(El(stamp(txt, sub, color, size), t0, t1, W / 2, cy, "slam", dout=0.15))

    # hook
    E.append(El(shear(text_img("THE BIGGEST RIVALRY", ANTON, 170, WHITE, stroke=8, shadow=14), 0.14),
                1.5, 4.0, W / 2, 760, "slam", dout=0.12))
    E.append(El(shear(text_img("IN THE WORLD", ANTON, 130, GOLD, stroke=8, shadow=12), 0.14),
                2.5, 4.0, W / 2, 925, "slam", dout=0.12))
    # title card
    a, b, vp, sub = title_card()
    E.append(El(a, 4.0, 7.9, W / 2 - 60, 300, "slide", din=0.3))
    E.append(El(b, 4.5, 7.9, W / 2 + 60, 780, "slide_r", din=0.3))
    E.append(El(vp, 5.0, 7.9, W / 2, 540, "slam"))
    E.append(El(sub, 6.0, 7.9, W / 2, 985, "rise", din=0.35))
    # persistent score-bug style ident
    E.append(El(bug(), 8.0, 57.0, 60 + bug().width / 2, 78, "slide", din=0.35, dout=0.3))

    # round 1
    lt("ROUND 1", "FIRST BATTER AT THE CREASE", 8.05, 9.45)
    st("FOUR!", "CRUNCHED TO THE BOUNDARY", 10.5, 12.4)
    cap("“TOO EASY.”", 12.6, 13.9)
    cap("SAME BALL. SAME PLAN.", 14.1, 15.4)
    st("FOUR MORE!", "BACK-TO-BACK BOUNDARIES", 16.5, 18.4, size=200)
    # change over
    E.append(El(ff_badge("FAST FORWARD 4X"), 18.5, 19.5, W - 250, 78, "slide_r", din=0.12, dout=0.1))
    cap("CHANGE OF BATTER", 18.55, 19.45)
    E.append(El(ff_badge("FAST FORWARD 2X"), 19.5, 21.5, W - 250, 78, "slide_r", din=0.12, dout=0.1))
    lt("ROUND 2", "THE CHALLENGER WALKS IN", 19.6, 21.45)
    cap("CONFIDENCE LEVEL: MAXIMUM", 21.7, 23.4)
    cap("LOCKED IN. EYES ON THE BALL.", 23.7, 25.4)
    # funny interruption
    E.append(El(ff_badge("FAST FORWARD 2X"), 25.5, 27.5, W - 250, 78, "slide_r", din=0.12, dout=0.1))
    cap("UNSCHEDULED PITCH INSPECTION", 25.65, 27.4)
    # no ball
    E.append(El(no_ball_band(), 28.5, 31.95, W / 2, 905, "wipe", dout=0.2))
    # dot ball
    cap("BIG SWING LOADING...", 32.1, 33.4)
    st("DOT BALL", "ALL POWER. ZERO RUNS.", 34.5, 35.9, color=WHITE, size=200)
    cap("WE DON'T TALK ABOUT THAT ONE.", 36.1, 37.4)
    # six
    cap("ONE MORE CHANCE...", 37.6, 39.4)
    st("SIX!", "ABSOLUTELY LAUNCHED", 41.0, 42.9, size=280, cy=770)
    cap("THAT SMILE SAYS IT ALL.", 43.2, 45.4)
    # aftermath
    lt("FULL-TIME DEBATE", "RIVALRY CONTINUES OFF THE PITCH", 45.6, 49.9)
    cap("FRIENDLY DISCUSSION. MOSTLY.", 50.2, 53.9)
    st("WHO WON?", None, 54.6, 56.9, size=230, cy=820)
    # end card
    q, n, p = end_card()
    E.append(El(q, 57.0, 61.1, W / 2, 400, "slam"))
    E.append(El(n, 57.5, 61.1, W / 2, 610, "rise", din=0.35))
    E.append(El(p, 58.0, 61.1, W / 2, 780, "rise", din=0.35))
    return E


# ------------------------------------------------------------------ per-frame camera
def zoom_at(seg, tr):
    k = seg["zoom"]
    if tr <= k[0][0]:
        return k[0][1:]
    for (t0, z0, x0, y0), (t1, z1, x1, y1) in zip(k, k[1:]):
        if tr <= t1:
            u = smooth((tr - t0) / (t1 - t0))
            return z0 + (z1 - z0) * u, x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
    return k[-1][1:]


def main():
    out = sys.argv[1]
    r0, r1 = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) > 3 else (0.0, TOTAL)
    els = build_elements()
    vig = vignette()
    black = Image.new("RGB", (W, H), (0, 0, 0))
    white = Image.new("RGB", (W, H), (255, 255, 255))
    alert = red_alert()
    nb_t = T("nb_reaction")
    rng = np.random.default_rng(7)

    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
         "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-profile:v", "high", "-g", "120",
         "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
         "-movflags", "+faststart", out], stdin=subprocess.PIPE)

    nbytes = W * H * 3
    for seg in SEGMENTS:
        n = round(seg["dur"] * FPS)
        f0 = round(seg["t0"] * FPS)
        if seg["t1"] <= r0 or seg["t0"] >= r1:
            continue
        a, b = seg["src"]
        vf = f"setpts=(PTS-STARTPTS)/{seg['speed']},fps={FPS}," + GRADE + (BG_EXTRA if seg.get("bg") else "")
        dec = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{a:.4f}", "-t", f"{b - a:.4f}", "-i", SRC,
                                "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        last = None
        for i in range(n):
            raw = dec.stdout.read(nbytes)
            if len(raw) < nbytes:
                raw = last
            last = raw
            t = (f0 + i) / FPS
            if t < r0 or t >= r1:
                continue
            tr = t - seg["t0"]
            z, cx, cy = zoom_at(seg, tr)
            # beat zoom punch
            for p in PUNCHES + FLASHES:
                if 0 <= t - p < 0.3:
                    z *= 1 + 0.07 * math.exp(-(t - p) / 0.07)
            sx = sy = 0.0
            for s0, sd in SHAKES:
                if 0 <= t - s0 < sd:
                    amp = 16 * (1 - (t - s0) / sd)
                    z = max(z, 1.04)
                    sx, sy = rng.uniform(-amp, amp), rng.uniform(-amp, amp)
            frame = Image.frombuffer("RGB", (W, H), raw, "raw", "RGB", 0, 1)
            if z > 1.001 or sx or sy:
                bw, bh = W / z, H / z
                x0 = min(max(cx * W - bw / 2 + sx, 0), W - bw)
                y0 = min(max(cy * H - bh / 2 + sy, 0), H - bh)
                frame = frame.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + bw, y0 + bh))
            else:
                frame = frame.copy()
            frame.paste(black, (0, 0), vig)
            # cinematic bars on slow motion
            if seg.get("bars"):
                bh = int(96 * min(ease_out(tr / 0.2), ease_out((seg["dur"] - tr) / 0.2)))
                if bh > 0:
                    frame.paste((0, 0, 0), (0, 0, W, bh))
                    frame.paste((0, 0, 0), (0, H - bh, W, H))
            # no-ball red alarm pulse
            if 0 <= t - nb_t < 2.0:
                pulse = (0.5 + 0.5 * math.cos((t - nb_t) * 2 * math.pi * 2)) * (1 - (t - nb_t) / 2.0)
                paste(frame, alert, 0, 0, 0.25 + 0.75 * pulse)
            for e in els:
                e.draw(frame, t)
            for fl in FLASHES:
                if 0 <= t - fl < 0.3:
                    al = 0.6 * math.exp(-(t - fl) / 0.07)
                    if al > 0.02:
                        frame = Image.blend(frame, white, al)
            enc.stdin.write(frame.tobytes())
        dec.stdout.close()
        dec.wait()
        print(f"{seg['name']:16s} done ({seg['t1']:.1f}s)", flush=True)
    enc.stdin.close()
    enc.wait()


if __name__ == "__main__":
    main()
