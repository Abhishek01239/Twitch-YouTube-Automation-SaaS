"""YouTube thumbnail (1280x720): split-screen face-off built from real source frames."""
import os, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source", "source_original.mp4")
ANTON = os.path.join(ROOT, "assets", "anton-latin-400-normal.woff")
BEBAS = os.path.join(ROOT, "assets", "bebas-neue-latin-400-normal.woff")
W, H = 1280, 720
GOLD, RED, WHITE, NAVY, INK = (255, 205, 40), (226, 30, 45), (255, 255, 255), (10, 16, 34), (8, 10, 18)

LEFT = dict(t=81.2, box=(100, 0, 700, 600))      # grey-shirt batter, big grin (face ~400,230)
RIGHT = dict(t=83.6, box=(600, 30, 1160, 590))   # black-shirt batter, pointing (face ~880,250)


def frame(t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", SRC, "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return Image.frombytes("RGB", (1280, 720), raw)


def grade(im):
    im = ImageEnhance.Contrast(im).enhance(1.18)
    im = ImageEnhance.Color(im).enhance(1.28)
    im = ImageEnhance.Brightness(im).enhance(1.04)
    a = np.asarray(im).astype(np.float32)
    a[..., 0] *= 1.04; a[..., 2] *= 0.94          # warm the cyan haze
    im = Image.fromarray(a.clip(0, 255).astype(np.uint8))
    return im.filter(ImageFilter.UnsharpMask(2, 90, 2))


def panel(spec, w):
    im = frame(spec["t"]).crop(spec["box"])
    im = grade(im)
    s = max(w / im.width, H / im.height)
    im = im.resize((int(im.width * s + .5), int(im.height * s + .5)), Image.LANCZOS)
    x = (im.width - w) // 2
    return im.crop((x, 0, x + w, H))


def text(txt, path, size, fill, stroke=0, sf=INK, shadow=10, k=0.14):
    f = ImageFont.truetype(path, size)
    tw = int(f.getlength(txt)); asc, desc = f.getmetrics(); p = stroke + shadow + 20
    img = Image.new("RGBA", (tw + 2 * p, asc + desc + 2 * p), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((p + shadow * .6, p + shadow * .6), txt, font=f, fill=(0, 0, 0, 200),
                            stroke_width=stroke, stroke_fill=(0, 0, 0, 200))
    img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(shadow * .6)))
    ImageDraw.Draw(img).text((p, p), txt, font=f, fill=fill, stroke_width=stroke, stroke_fill=sf)
    if k:
        pad = int(k * img.height) + 2
        o = Image.new("RGBA", (img.width + pad, img.height), (0, 0, 0, 0)); o.paste(img, (pad, 0))
        img = o.transform(o.size, Image.AFFINE, (1, k, -k * img.height, 0, 1, 0), Image.BICUBIC)
    return img.crop(img.getbbox())


def main(out):
    left, right = panel(LEFT, 720), panel(RIGHT, 720)
    canvas = Image.new("RGB", (W, H))
    canvas.paste(right, (W - 720 + 20, 0))
    lp = Image.new("RGB", (W, H)); lp.paste(left, (-30, 0))
    top, bot = 668, 600  # slanted divider
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon([(0, 0), (top, 0), (bot, H), (0, H)], fill=255)
    canvas.paste(lp, (0, 0), mask)
    canvas = canvas.convert("RGBA")

    # vignette for depth and text contrast
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / 1.414
    v = Image.fromarray((np.clip((r - .45) / .55, 0, 1) ** 1.6 * 170).astype(np.uint8))
    canvas.paste((0, 0, 0, 255), (0, 0), v)
    # bottom fade behind the title banner
    g = Image.fromarray(np.tile((np.clip((np.arange(H) - 440) / 280, 0, 1) ** 1.3 * 210).astype(np.uint8)[:, None], (1, W)))
    canvas.paste((0, 0, 0, 255), (0, 0), g)
    g2 = Image.fromarray(np.tile((np.clip((150 - np.arange(H)) / 150, 0, 1) ** 1.5 * 150).astype(np.uint8)[:, None], (1, W)))
    canvas.paste((0, 0, 0, 255), (0, 0), g2)

    d = ImageDraw.Draw(canvas)
    # glowing divider: gold core, white edge
    for wdt, col in [(30, (255, 205, 40, 90)), (16, GOLD + (255,)), (5, WHITE + (255,))]:
        d.line([(top, -10), (bot, H + 10)], fill=col, width=wdt)

    # VS badge
    cx, cy = (top + bot) // 2 - 4, 360
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([cx - 120, cy - 120, cx + 120, cy + 120], fill=(255, 60, 30, 170))
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(40)))
    d = ImageDraw.Draw(canvas)
    d.ellipse([cx - 92, cy - 92, cx + 92, cy + 92], fill=INK, outline=GOLD, width=10)
    d.ellipse([cx - 76, cy - 76, cx + 76, cy + 76], fill=RED)
    vs = text("VS", ANTON, 120, WHITE, stroke=5, shadow=6, k=0.12)
    canvas.alpha_composite(vs, (cx - vs.width // 2, cy - vs.height // 2 + 4))

    # hook: top-left
    h1 = text("BIGGEST", ANTON, 96, WHITE, stroke=6)
    h2 = text("RIVALRY!", ANTON, 96, GOLD, stroke=6)
    hx = (W - h1.width - h2.width + 10) // 2
    canvas.alpha_composite(h1, (hx, 0))
    canvas.alpha_composite(h2, (hx + h1.width - 10, 0))

    # NO BALL tag, top-right
    tag = text("NO BALL?!", ANTON, 58, WHITE, stroke=0, shadow=0, k=0)
    tp = Image.new("RGBA", (tag.width + 70, tag.height + 34), (0, 0, 0, 0))
    ImageDraw.Draw(tp).polygon([(22, 0), (tp.width, 0), (tp.width - 22, tp.height), (0, tp.height)], fill=RED + (255,))
    ImageDraw.Draw(tp).polygon([(22, 0), (34, 0), (12, tp.height), (0, tp.height)], fill=GOLD + (255,))
    tp.alpha_composite(tag, (40, 17))
    tp = tp.rotate(6, Image.BICUBIC, expand=True)
    canvas.alpha_composite(tp, (W - tp.width - 10, 238))

    # title banner, bottom
    t = text("SUNNY SIR  VS  KD SIR", ANTON, 104, WHITE, stroke=6, shadow=10, k=0.12)
    bw = t.width + 90
    bx, by = (W - bw) // 2, H - t.height - 50
    band = Image.new("RGBA", (bw + 40, t.height + 30), (0, 0, 0, 0))
    ImageDraw.Draw(band).polygon([(30, 0), (band.width, 0), (band.width - 30, band.height), (0, band.height)], fill=NAVY + (230,))
    ImageDraw.Draw(band).rectangle([0, band.height - 9, band.width, band.height], fill=GOLD + (255,))
    canvas.alpha_composite(band, (bx - 20, by - 4))
    canvas.alpha_composite(t, ((W - t.width) // 2, by + 8))

    canvas = canvas.convert("RGB")
    canvas.save(out, quality=95, optimize=True)
    canvas.resize((320, 180), Image.LANCZOS).save(out.replace(".jpg", "_small_preview.jpg"), quality=90)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "export", "Thumbnail_Sunny_vs_KD.jpg"))
