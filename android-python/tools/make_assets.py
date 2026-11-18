"""Generate the Vooc launcher icon + splash screen (acid-lime theme).

Run from android-python/:  python tools/make_assets.py   (needs Pillow)
Everything is drawn at 4x and downsampled for crisp edges. Colours come from
the app theme (vooc/m3.py): lime #C6FF00, deep green-black #0C0E0A.
"""
import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

LIME, LIME_HI, LIME_LO = (198, 255, 0), (222, 255, 70), (150, 210, 0)
INK, BG = (12, 14, 10), (12, 14, 10)
BARS = [.38, .68, 1.0, .60, .82]          # equaliser glyph, matches the in-app logo
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
SS = 4
FONTS = ["/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
FONTS_REG = ["/usr/share/fonts/opentype/inter/Inter-Medium.otf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def font(paths, size):
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def lime_gradient(w, h):
    top = Image.linear_gradient("L").resize((w, h))          # 0 (top) -> 255 (bottom)
    return Image.composite(Image.new("RGB", (w, h), LIME_LO), Image.new("RGB", (w, h), LIME_HI), top)


def glyph(draw, cx, cy, height, color):
    """Five rounded bars centred on (cx, cy); `height` = tallest bar."""
    bw = height * .15
    gap = height * .10
    total = len(BARS) * bw + (len(BARS) - 1) * gap
    x = cx - total / 2
    for r in BARS:
        h = height * r
        draw.rounded_rectangle((x, cy - h / 2, x + bw, cy + h / 2), radius=bw / 2, fill=color)
        x += bw + gap


def save(img, name, size=None):
    if size:
        img = img.resize(size, Image.LANCZOS)
    os.makedirs(OUT, exist_ok=True)
    img.save(os.path.join(OUT, name), optimize=True)
    print("wrote", name, img.size)


def icons(n=1024):
    s = n * SS
    # adaptive background: lime gradient with a soft highlight (full bleed, no transparency)
    bg = lime_gradient(s, s)
    hl = Image.new("L", (s, s), 0)
    ImageDraw.Draw(hl).ellipse((s * .05, -s * .25, s * .95, s * .55), fill=38)
    hl = hl.filter(ImageFilter.GaussianBlur(s * .08))
    bg = Image.composite(Image.new("RGB", (s, s), (255, 255, 220)), bg, hl)
    save(bg, "icon_bg.png", (n, n))
    # adaptive foreground: dark glyph inside the 66% safe zone, transparent elsewhere
    fg = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    glyph(ImageDraw.Draw(fg), s / 2, s / 2, s * .46, INK + (255,))
    save(fg, "icon_fg.png", (n, n))
    # legacy / store icon: full-bleed rounded tile
    tile = bg.convert("RGBA")
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * .22), fill=255)
    tile.putalpha(mask)
    tile.alpha_composite(fg)
    save(tile, "icon.png", (n, n))


def splash(w=1440, h=3040):
    sw, sh = w * SS // 2, h * SS // 2                         # 2x supersample is plenty here
    img = Image.new("RGB", (sw, sh), BG)
    glow = Image.new("L", (sw, sh), 0)
    gd = ImageDraw.Draw(glow)
    cx, cy = sw // 2, int(sh * .44)
    r = int(sw * .62)
    gd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=95)
    glow = glow.filter(ImageFilter.GaussianBlur(sw * .16))
    img = Image.composite(Image.new("RGB", (sw, sh), (60, 90, 0)), img, glow)
    d = ImageDraw.Draw(img)
    t = int(sw * .34)                                         # logo tile size
    x0, y0 = cx - t // 2, cy - t // 2
    tile = lime_gradient(t, t)
    m = Image.new("L", (t, t), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, t - 1, t - 1), radius=int(t * .26), fill=255)
    img.paste(tile, (x0, y0), m)
    glyph(d, cx, cy, t * .46, INK)
    d.text((cx, cy + t // 2 + sw * .09), "VOOC", font=font(FONTS, int(sw * .105)), fill=LIME, anchor="mm")
    d.text((cx, cy + t // 2 + sw * .19), "AUDIO VISUALIZER", font=font(FONTS_REG, int(sw * .034)),
           fill=(163, 173, 152), anchor="mm")
    save(img, "presplash.png", (w, h))


if __name__ == "__main__":
    icons()
    splash()
