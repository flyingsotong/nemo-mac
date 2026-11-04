"""Build the images the README and the repository page use.

Everything here is drawn by the same renderer the app uses, over a backdrop colour
sampled from a real capture of the glass pill, so the pictures cannot drift from
the product. The menu shot is a real screenshot, cropped to the panel.

Run:  .venv/bin/python scripts/make_media.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overlay_render import ACCENT, FG, H, MUTED, R, W, render  # noqa: E402

OUT = ROOT / "docs"
SCALE = 2
GLASS = (44, 44, 46, 240)        # sampled from a real capture of the pill
SHADOW = (0, 0, 0, 90)


def _font(px: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in ("/System/Library/Fonts/Helvetica.ttc",
                 "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else
                 "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, px)
            except Exception:
                continue
    return ImageFont.load_default()


def _capsule(size: tuple[int, int]) -> Image.Image:
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, w - 1, h - 1],
                                          radius=R * SCALE, fill=GLASS)
    return img


def pill(label: str, phase: float, hist) -> Image.Image:
    """The pill exactly as the window shows it: capsule plus renderer content."""
    body = _capsule((W * SCALE, H * SCALE))
    body.alpha_composite(render(label, phase, hist, scale=SCALE, glass=True))
    return body


def _backdrop(size: tuple[int, int]) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    top, bottom = (28, 30, 35), (12, 13, 16)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t)
                                            for i in range(3)))
    # a soft warm glow so the shot is not a flat slab
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([w // 2 - 420, h - 320, w // 2 + 420, h + 220],
                                 fill=(242, 178, 62, 26))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    return img


def _with_shadow(canvas: Image.Image, body: Image.Image, xy: tuple[int, int]) -> None:
    shadow = Image.new("RGBA", body.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 120), (0, 0), body.getchannel("A"))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas.alpha_composite(shadow, (xy[0] + 2, xy[1] + 14))
    canvas.alpha_composite(body, xy)


def hero() -> None:
    canvas = _backdrop((1600, 620)).convert("RGBA")
    body = pill("listening", 0.7, [0.15, 0.35, 0.6, 0.85, 1.0, 0.75, 0.5, 0.3, 0.2])
    _with_shadow(canvas, body, ((1600 - body.width) // 2, 250))
    canvas.convert("RGB").save(OUT / "hero.png", optimize=True)
    print("docs/hero.png")


def states() -> None:
    labels = [
        ("listening", [0.2, 0.45, 0.8, 1.0, 0.7, 0.4, 0.25, 0.5, 0.3]),
        ("transcribing", None), ("done", None), ("error", None),
        ("alert:No mic audio", None), ("paused", None),
        ("say:Reloaded", None), ("hint:Hold Right Command to talk", None),
    ]
    body_w = W * SCALE
    pad, gap = 28, 16
    width = body_w + pad * 2
    height = pad * 2 + len(labels) * (H * SCALE + gap) - gap
    canvas = Image.new("RGBA", (width, height), (18, 19, 22, 255))
    for i, (label, hist) in enumerate(labels):
        body = pill(label, 0.6, hist or [0.0] * 9)
        y = pad + i * (H * SCALE + gap)
        canvas.alpha_composite(body, (pad, y))
    canvas.convert("RGB").save(OUT / "pill-states.png", optimize=True)
    print("docs/pill-states.png")


def social() -> None:
    canvas = _backdrop((1280, 640)).convert("RGBA")
    d = ImageDraw.Draw(canvas)
    d.text((80, 150), "Nemo for Mac", font=_font(76, True), fill=FG)
    d.text((80, 250), "Hold Right Command, speak, let go.", font=_font(30), fill=MUTED)
    d.text((80, 296), "Whisper on Metal. Offline, ~300 ms.", font=_font(30), fill=ACCENT)
    body = pill("listening", 0.7, [0.15, 0.35, 0.6, 0.85, 1.0, 0.75, 0.5, 0.3, 0.2])
    _with_shadow(canvas, body, (80, 400))
    canvas.convert("RGB").save(OUT / "social-preview.png", optimize=True)
    print("docs/social-preview.png")


def icon_states() -> None:
    src = Path("/tmp/icon-compare.png")
    if not src.exists():
        print("skip icon states: no source capture")
        return
    Image.open(src).save(OUT / "menubar-icon.png", optimize=True)
    print("docs/menubar-icon.png")


def menu() -> None:
    """Crop the real menu screenshot to the panel.

    Fixed geometry: the menu is a translucent panel, so it cannot be separated from
    a light window behind it by colour alone. This crop was measured by eye once.
    """
    src = Path("/tmp/menu-dark.png")
    if not src.exists():
        print("skip menu: no source capture")
        return
    Image.open(src).crop((1934, 62, 2530, 830)).save(OUT / "menu.png", optimize=True)
    print("docs/menu.png")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    hero()
    states()
    social()
    menu()
    icon_states()
