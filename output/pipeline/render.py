"""Frame renderer: AI keyframes -> animated cinematic shots with camera moves, true multi-sample
motion blur, grading, bloom, police lights, rain, speed streaks, HUD and titles."""
import numpy as np, math, os, sys, subprocess, functools
from multiprocessing import Pool
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from timeline import *

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "img")
FONT = os.path.join(HERE, "fonts")
NF = int(round(DURATION * FPS))

# ------------------------------------------------------------------ setup
SRC = {}
VIG = POL_L = POL_R = POL_TOP = GRAIN = None
RAIN = STREAK = None

def prep(name):
    im = Image.open(os.path.join(IMG, name + ".jpg")).convert("RGB")
    w, h = im.size
    im = im.crop((0, 0, w, h - int(h * 0.045)))  # drop generator watermark strip
    w, h = im.size
    sc = 2.45 if h > w else 3.6
    im = im.resize((int(w * sc), int(h * sc)), Image.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=3, percent=70, threshold=2))
    return im

def init():
    global VIG, POL_L, POL_R, POL_TOP, GRAIN, RAIN, STREAK
    for s in SHOTS:
        if s[2] not in SRC: SRC[s[2]] = prep(s[2])
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    nx, ny = (xx - W / 2) / (W / 2), (yy - H / 2) / (H / 2)
    VIG = (1 - 0.42 * np.clip((nx ** 2 * 0.9 + ny ** 2 * 0.55) - 0.15, 0, 1) ** 1.2)[..., None].astype(np.float32)
    g = lambda cx, cy, r: np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * r * r))).astype(np.float32)
    POL_L = g(W * 0.05, H * 0.30, 520) + 0.5 * g(W * 0.3, H * 0.75, 600)
    POL_R = g(W * 0.95, H * 0.28, 520) + 0.5 * g(W * 0.7, H * 0.8, 600)
    POL_TOP = g(W * 0.5, -200, 900)
    r = np.random.default_rng(3)
    GRAIN = [r.normal(0, 1, (H // 2, W // 2)).astype(np.float32) for _ in range(6)]
    RAIN = r.random((420, 4))  # x, y, speed, length
    STREAK = r.random((70, 4))  # angle, r0, speed, hue

# ------------------------------------------------------------------ helpers
def ease(u, kind):
    u = min(max(u, 0.0), 1.0)
    if kind == "lin": return u
    if kind == "in": return u * u
    if kind == "out": return 1 - (1 - u) ** 2
    return u * u * (3 - 2 * u)

def shot_at(t):
    for i, s in enumerate(SHOTS):
        if b(s[0]) <= t < b(s[1]): return i
    return len(SHOTS) - 1

def shake_amp(fx):
    return 0.0 + 4 * ("shake1" in fx) + 9 * ("shake2" in fx) + 16 * ("shake3" in fx)

def sample(idx, t):
    """Render the geometric camera view of shot idx at time t (PIL image)."""
    sb, eb, name, mv, fx = SHOTS[idx]
    t0, t1 = b(sb), b(eb)
    u = ease((t - t0) / (t1 - t0), mv["ease"])
    lerp = lambda a: a[0] + (a[1] - a[0]) * u
    z, cx, cy, rot = lerp(mv["z"]), lerp(mv["x"]), lerp(mv["y"]), lerp(mv["r"])
    if "walk" in fx:
        cy += 0.006 * math.sin(2 * math.pi * t / (2 * BEAT)); rot += 0.5 * math.sin(2 * math.pi * t / (4 * BEAT))
    # punch-in at the start of every shot, zoom-out whip before big cuts
    dt_in = t - t0
    big_in = any(abs(t0 - c) < 1e-3 for c in BIG_CUTS)
    z *= 1 + (0.18 if big_in else 0.06) * math.exp(-dt_in / 0.09)
    dt_out = t1 - t
    if any(abs(t1 - c) < 1e-3 for c in BIG_CUTS) and dt_out < 0.16:
        z *= 1 + 0.35 * (1 - dt_out / 0.16) ** 2
    # handheld / impact shake (sum of sines + beat kicks)
    amp = shake_amp(fx)
    bp_ = (t % BEAT) / BEAT
    kick = math.exp(-bp_ * 6) if ("shake2" in fx or "shake3" in fx) else 0
    sx = amp * (math.sin(t * 13.1) * .6 + math.sin(t * 29.7 + 1) * .4) + amp * 1.2 * kick * math.sin(t * 91)
    sy = amp * (math.sin(t * 11.3 + 2) * .6 + math.sin(t * 23.9) * .4) + amp * 1.2 * kick * math.cos(t * 83)
    rot += amp * 0.03 * math.sin(t * 7.7)
    im = SRC[name]
    sw, sh = im.size
    th = math.radians(rot)
    z *= 1 + abs(math.sin(th)) * 1.9
    s = max(W / sw, H / sh) * z  # output px per source px
    hw, hh = W / 2 / s, H / 2 / s
    px = min(max(cx * sw, hw), sw - hw); py = min(max(cy * sh, hh), sh - hh)
    px += sx / s; py += sy / s
    c, si = math.cos(th) / s, math.sin(th) / s
    a, b_, d, e = c, si, -si, c
    cc = px - a * W / 2 - b_ * H / 2
    f = py - d * W / 2 - e * H / 2
    return im.transform((W, H), Image.AFFINE, (a, b_, cc, d, e, f), resample=Image.BICUBIC)

def view(idx, t):
    fx = SHOTS[idx][4]
    n = 3 if (fx & {"shake2", "shake3", "streaks"}) else 2
    shutter = 1 / 60  # 180-degree shutter at 30 fps
    acc = None
    for k in range(n):
        tt = t - shutter * k / max(1, n - 1)
        tt = max(tt, b(SHOTS[idx][0]))
        a = np.asarray(sample(idx, tt), dtype=np.float32)
        acc = a if acc is None else acc + a
    return acc / (n * 255.0)

# ------------------------------------------------------------------ fx
def grade(x):
    lum = (x[..., 0] * .3 + x[..., 1] * .59 + x[..., 2] * .11)[..., None]
    x = lum + (x - lum) * 1.18  # saturation
    x = np.clip(x, 0, 1)
    x = x * 0.62 + 0.38 * x * x * (3 - 2 * x)  # S-curve contrast
    sh = (1 - lum) ** 2; hl = lum ** 2
    x = x + sh * np.array([-0.01, 0.025, 0.05], np.float32) + hl * np.array([0.05, 0.0, 0.03], np.float32)
    return x

def bloom(x, strength=0.45):
    small = Image.fromarray((np.clip(x, 0, 1) * 255).astype(np.uint8)).resize((W // 6, H // 6), Image.BILINEAR)
    arr = np.asarray(small, dtype=np.float32) / 255
    arr = np.clip(arr - 0.55, 0, 1) * 2.2
    bl = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(9))
    bl = np.asarray(bl.resize((W, H), Image.BILINEAR), dtype=np.float32) / 255
    return x + bl * strength

def police(x, t, k=1.0):
    ph = (t * 7.0) % 2
    on = (t * 14) % 1 < 0.6
    r = (1.0 if ph < 1 else 0.15) * on
    bl = (1.0 if ph >= 1 else 0.15) * on
    x = x + POL_L[..., None] * np.array([0.9, 0.05, 0.08], np.float32) * (r * 0.55 * k)
    x = x + POL_R[..., None] * np.array([0.05, 0.25, 1.0], np.float32) * (bl * 0.55 * k)
    x = x + POL_TOP[..., None] * (np.array([0.7, 0.05, 0.1], np.float32) * r + np.array([0.05, 0.2, 0.9], np.float32) * bl) * 0.25 * k
    return x

def overlay_rain(img, t):
    d = ImageDraw.Draw(img, "RGBA")
    for x0, y0, sp, ln in RAIN:
        y = (y0 * H + t * (1800 + 1600 * sp)) % (H + 200) - 100
        x = (x0 * W + y * 0.18) % W
        L = 30 + 60 * ln
        d.line([(x, y), (x + L * 0.18, y + L)], fill=(200, 220, 255, int(40 + 50 * sp)), width=2)

def overlay_streaks(img, t):
    d = ImageDraw.Draw(img, "RGBA")
    for ang, r0, sp, hue in STREAK:
        A = ang * 2 * math.pi
        r = ((r0 + t * (1.6 + 2.5 * sp)) % 1.0)
        R0 = 250 + r * 1100; R1 = R0 + 120 + 380 * r
        col = (255, 80, 200, int(110 * r)) if hue < .5 else (90, 230, 255, int(110 * r))
        d.line([(W / 2 + math.cos(A) * R0, H * .55 + math.sin(A) * R0),
                (W / 2 + math.cos(A) * R1, H * .55 + math.sin(A) * R1)], fill=col, width=3)

@functools.lru_cache(64)
def font(name, size):
    return ImageFont.truetype(os.path.join(FONT, name), size)

def text(img, s, fname, size, cy, fill=(255, 255, 255), glow=(255, 40, 180), alpha=1.0, cx=W / 2,
         glow_r=16, spacing=0, stroke=0):
    if alpha <= 0.01: return
    f = font(fname, max(8, int(size)))
    if spacing:
        widths = [f.getlength(ch) for ch in s]; tw = sum(widths) + spacing * (len(s) - 1)
    else:
        tw = f.getlength(s)
    asc, desc = f.getmetrics(); th = asc + desc
    pad = glow_r * 3 + 10
    cw, ch_ = int(tw + 2 * pad), int(th + 2 * pad)
    mask = Image.new("L", (cw, ch_), 0); md = ImageDraw.Draw(mask)
    if spacing:
        x = pad
        for ch, wd in zip(s, widths): md.text((x, pad), ch, font=f, fill=255, stroke_width=stroke, stroke_fill=255); x += wd + spacing
    else:
        md.text((pad, pad), s, font=f, fill=255, stroke_width=stroke, stroke_fill=255)
    ox, oy = int(cx - cw / 2), int(cy - ch_ / 2)
    if glow:
        gm = mask.filter(ImageFilter.GaussianBlur(glow_r)).point(lambda v: min(255, int(v * 2.2 * alpha)))
        img.paste(Image.new("RGB", (cw, ch_), glow), (ox, oy), gm)
    shadow = mask.filter(ImageFilter.GaussianBlur(3)).point(lambda v: int(v * 0.6 * alpha))
    img.paste(Image.new("RGB", (cw, ch_), (0, 0, 0)), (ox + 4, oy + 5), shadow)
    img.paste(Image.new("RGB", (cw, ch_), fill), (ox, oy), mask.point(lambda v: int(v * alpha)))

def star(d, cx, cy, r, fill, outline):
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=fill, outline=outline, width=4)

def hud_wanted(img, t):
    d = ImageDraw.Draw(img, "RGBA")
    n = min(5, 1 + int((t - CHASE) / (2 * BEAT)))
    for k in range(5):
        cx = W - 70 - (4 - k) * 78; cy = 170
        lit = k < n
        blink = lit and k == n - 1 and (t * 4) % 1 < 0.5 and n < 5
        fill = (255, 255, 255, 235) if lit and not blink else (40, 40, 40, 150)
        star(d, cx, cy, 32, fill, (0, 0, 0, 220))

# ------------------------------------------------------------------ titles
def titles(img, t):
    def fin(a, d=0.25): return min(1, max(0, (t - a) / d))
    def fout(a, d=0.25): return min(1, max(0, (a - t) / d))
    # HOOK 0 - DROP
    if t < DROP:
        a = fin(0.05, 0.08) * fout(DROP, 0.08)
        pop = 1 + 0.25 * math.exp(-t / 0.08)
        text(img, "THIS IS", "Oswald.ttf", 70 * pop, 700, alpha=a, glow=(0, 0, 0), spacing=12)
        text(img, "VICE CITY", "Anton.ttf", 190 * pop, 840, alpha=a, glow=(255, 30, 120), glow_r=22)
        if t > 0.86:
            text(img, "IN 2026", "Anton.ttf", 120 * (1 + 0.3 * math.exp(-(t - .86) / 0.07)), 1010, fill=(255, 220, 90), glow=(255, 90, 0), alpha=a)
    # Title card
    if DROP <= t < CAR:
        a = fout(CAR - 0.05, 0.3)
        # neon flicker-on
        fl = 1.0
        tt = t - DROP
        if tt < 0.5: fl = 1.0 if (int(tt * 30) % 3 != 1) else 0.25
        text(img, "W E L C O M E   T O", "Oswald.ttf", 64, 640, alpha=a * fin(DROP, 0.2), glow=(0, 160, 255), glow_r=12)
        text(img, "Vice City", "Yellowtail.ttf", 250 + 20 * tt, 820, fill=(255, 235, 250), glow=(255, 20, 170),
             alpha=a * fl, glow_r=26)
        text(img, "FAN-MADE CINEMATIC CONCEPT  ·  NOT OFFICIAL FOOTAGE", "Oswald.ttf", 30, H - 150,
             fill=(230, 230, 230), glow=None, alpha=0.85 * a * fin(DROP + .3, .3))
    # Character lower third
    if b(30) <= t < b(38):
        a = fin(b(30), 0.2) * fout(b(38), 0.2)
        slide = (1 - fin(b(30), 0.35)) * 300
        text(img, "RICO VEGA", "Anton.ttf", 150, H - 520, cx=W / 2 - slide, alpha=a, glow=(255, 30, 160), glow_r=18)
        text(img, "VICE CITY'S MOST WANTED", "Oswald.ttf", 52, H - 400, cx=W / 2 + slide, alpha=a,
             fill=(120, 240, 255), glow=(0, 120, 255), glow_r=10, spacing=4)
    # Chase slam
    if CHASE <= t < CHASE + 0.9:
        a = fout(CHASE + 0.9, 0.2)
        text(img, "WANTED", "Anton.ttf", 230 * (1 + 0.35 * math.exp(-(t - CHASE) / 0.07)), 960, fill=(255, 255, 255),
             glow=(255, 0, 40), alpha=a, glow_r=24)
    # Ending
    if ENDING + 0.4 <= t < ENDCARD:
        a = fin(ENDING + 0.4, 0.5) * fout(ENDCARD, 0.3)
        text(img, "THE CITY NEVER SLEEPS", "Oswald.ttf", 70, 520, alpha=a, glow=(120, 0, 255), spacing=6)
    if t >= ENDCARD:
        a = fin(ENDCARD + 0.2, 0.5)
        text(img, "Vice City", "Yellowtail.ttf", 270, 560, fill=(255, 235, 250), glow=(255, 20, 170), alpha=a, glow_r=28)
        text(img, "COMING  SOON", "Anton.ttf", 90, 760, alpha=fin(ENDCARD + .7, .4), glow=(0, 150, 255), spacing=8)
        a2 = fin(ENDCARD + 1.3, 0.4)
        text(img, "GALAXY OF GAMES AR", "Anton.ttf", 66, H - 330, fill=(255, 220, 90), glow=(255, 90, 0), alpha=a2, spacing=4)
        text(img, "SUBSCRIBE FOR MORE", "Oswald.ttf", 48, H - 245, alpha=a2, glow=(255, 0, 60), spacing=6)
        text(img, "Fan-made concept · Not official gameplay", "Oswald.ttf", 28, H - 160, glow=None, alpha=0.8 * a2)

# ------------------------------------------------------------------ frame
def render(i):
    t = i / FPS
    idx = shot_at(t)
    sb, eb, name, mv, fx = SHOTS[idx]
    x = view(idx, t)
    # soft dissolve into the end card shot
    for c in SOFT_CUTS:
        if c - 0.5 <= t < c and idx + 1 < len(SHOTS):
            w = (t - (c - 0.5)) / 0.5
            x = x * (1 - w) + view(idx + 1, c) * w
    x = grade(x)
    if "police" in fx: x = police(x, t, 1.0)
    if "police_far" in fx: x = police(x, t, 0.25)
    if "club" in fx:
        bp_ = (t % BEAT) / BEAT
        pulse = math.exp(-bp_ * 5)
        col = np.array([0.5, 0.05, 0.45], np.float32) if int(t / BEAT) % 2 else np.array([0.0, 0.35, 0.55], np.float32)
        x = x + POL_TOP[..., None] * col * 0.5 * pulse
        if "strobe" in fx and (i % 4 == 0): x = x * 1.35 + 0.05
    if "sun" in fx:
        x = x + POL_TOP[..., None] * np.array([0.35, 0.15, 0.05], np.float32) * (0.6 + 0.4 * math.sin(t * 2))
    x = bloom(x, 0.55 if (fx & {"police", "club"}) else 0.4)
    x = x * VIG
    g = GRAIN[i % len(GRAIN)]
    g = np.repeat(np.repeat(g, 2, 0), 2, 1)[..., None]
    x = x + g * 0.018
    # cut flashes + chromatic aberration
    tin = t - b(sb)
    big = any(abs(b(sb) - c) < 1e-3 for c in BIG_CUTS)
    if sb > 0 and tin < 0.2:
        fl = (0.9 if big else 0.3) * math.exp(-tin / (0.06 if big else 0.03))
        x = x + fl
    ca = 0
    if tin < 0.15 and sb > 0: ca = int(14 * (1 - tin / 0.15)) if big else int(6 * (1 - tin / 0.15))
    if "shake3" in fx: ca = max(ca, int(4 * math.exp(-((t % BEAT) / BEAT) * 6)))
    x = np.clip(x, 0, 1)
    if ca:
        x[..., 0] = np.roll(x[..., 0], ca, 1); x[..., 2] = np.roll(x[..., 2], -ca, 1)
    # fade in from black very first frames / out at end
    if t < 0.08: x *= t / 0.08 * 0.7 + 0.3
    if t > DURATION - 0.6: x *= max(0, (DURATION - t) / 0.6)
    img = Image.fromarray((x * 255).astype(np.uint8))
    if "rain" in fx: overlay_rain(img, t)
    if "streaks" in fx: overlay_streaks(img, t)
    if "wanted" in fx: hud_wanted(img, t)
    titles(img, t)
    if t > DURATION - 0.6:
        img = Image.blend(Image.new("RGB", img.size), img, max(0, (DURATION - t) / 0.6))
    return img.tobytes()

if __name__ == "__main__":
    out = sys.argv[1]
    frames = [int(a) for a in sys.argv[2].split(",")] if len(sys.argv) > 2 else None
    if frames:  # preview stills
        init()
        for f in frames:
            Image.frombytes("RGB", (W, H), render(f)).save(f"{out}/f{f:04d}.jpg", quality=90)
        sys.exit()
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                           "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.2", out], stdin=subprocess.PIPE)
    with Pool(4, initializer=init) as p:
        for k, fr in enumerate(p.imap(render, range(NF), chunksize=3)):
            ff.stdin.write(fr)
            if k % 60 == 0: print(k, "/", NF, flush=True)
    ff.stdin.close(); ff.wait()
    print("done", out)
