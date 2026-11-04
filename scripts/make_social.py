"""Build the Open Graph card.

GitHub shows it at 1280x640; the rest of the web expects 1200x630. Both are drawn
from one layout so they cannot disagree, and the pill in them comes from the app's
own renderer rather than a drawing of it.

Run:  .venv/bin/python scripts/make_social.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overlay_render import ACCENT, BG_BOT, FG, MUTED, render, W, H  # noqa: E402

OUT = ROOT / "docs"
GLASS = (44, 44, 46, 240)
PILL_SCALE = 2

REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def font(px: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in ((BOLD, REG) if bold else (REG, BOLD)):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, px)
            except Exception:
                continue
    return ImageFont.load_default()


def backdrop(size: tuple[int, int]) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    top, bottom = (34, 37, 42), (11, 12, 14)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)],
               fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([int(w * 0.42), int(h * 0.55), int(w * 1.05), int(h * 1.35)],
               fill=(242, 178, 62, 30))
    gd.ellipse([-int(w * 0.2), -int(h * 0.4), int(w * 0.35), int(h * 0.5)],
               fill=(90, 120, 180, 18))
    glow = glow.filter(ImageFilter.GaussianBlur(int(h * 0.09)))
    return Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")


def pill_body() -> Image.Image:
    body = Image.new("RGBA", (W * PILL_SCALE, H * PILL_SCALE), (0, 0, 0, 0))
    ImageDraw.Draw(body).rounded_rectangle(
        [0, 0, body.width - 1, body.height - 1], radius=20 * PILL_SCALE, fill=GLASS)
    body.alpha_composite(render("listening", 0.7,
                                [0.15, 0.35, 0.6, 0.85, 1.0, 0.75, 0.5, 0.3, 0.2],
                                scale=PILL_SCALE, glass=True))
    return body


def waveform(height: int, colour=ACCENT) -> Image.Image:
    """The menu bar icon, at poster size."""
    bars = [10, 18, 28, 16, 34, 16, 28, 18, 10]
    unit = height / 34
    width = int(44 * unit)
    img = Image.new("RGBA", (width, int(height * 1.35)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = 4 * unit
    for hgt in bars:
        bar_h = hgt * unit
        y0 = (img.height - bar_h) / 2
        d.rounded_rectangle([x, y0, x + 2 * unit, y0 + bar_h],
                            radius=max(1, unit), fill=colour + (235,))
        x += 4 * unit
    return img


def card(size: tuple[int, int]) -> Image.Image:
    w, h = size
    img = backdrop(size).convert("RGBA")
    d = ImageDraw.Draw(img)
    pad = int(w * 0.07)

    # wordmark, on one baseline so "for Mac" reads as a suffix, not a subtitle
    big, small = font(int(h * 0.115), True), font(int(h * 0.062))
    baseline = int(h * 0.28)
    d.text((pad, baseline), "Nemo", font=big, fill=FG, anchor="ls")
    nemo_w = d.textlength("Nemo", font=big)
    d.text((pad + nemo_w + int(w * 0.016), baseline), "for Mac", font=small,
           fill=ACCENT, anchor="ls")

    d.text((pad, int(h * 0.36)), "Hold Right Command, speak, let go.",
           font=font(int(h * 0.048)), fill=FG)
    d.text((pad, int(h * 0.46)), "Whisper on Metal  ·  offline  ·  301 ms to text",
           font=font(int(h * 0.038)), fill=MUTED)

    body = pill_body()
    body = body.resize((int(body.width * 1.15), int(body.height * 1.15)))
    shadow = Image.new("RGBA", body.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 130), (0, 0), body.getchannel("A"))
    shadow = shadow.filter(ImageFilter.GaussianBlur(16))
    py = int(h * 0.64)
    img.alpha_composite(shadow, (pad + 2, py + 12))
    img.alpha_composite(body, (pad, py))

    # the icon sitting on a line, so the label "menu bar" has something to mean
    icon = waveform(int(h * 0.10))
    ix, iy = w - pad - icon.width, int(h * 0.20)
    bar_y = iy + int(icon.height * 0.94)
    d.line([(ix - int(w * 0.02), bar_y), (ix + icon.width + int(w * 0.02), bar_y)],
           fill=(255, 255, 255, 28), width=2)
    img.alpha_composite(icon, (ix, iy))
    d.text((ix + icon.width // 2, bar_y + int(h * 0.035)), "menu bar",
           font=font(int(h * 0.028)), fill=MUTED, anchor="ma")

    d.text((pad, int(h * 0.885)), "MIT  ·  no account, no cloud, no telemetry",
           font=font(int(h * 0.030)), fill=MUTED, anchor="la")
    d.text((w - pad, int(h * 0.885)), "github.com/flyingsotong/nemo-mac",
           font=font(int(h * 0.030)), fill=MUTED, anchor="ra")
    return img.convert("RGB")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name, size in (("social-preview.png", (1280, 640)),
                       ("og.png", (1200, 630))):
        card(size).save(OUT / name, optimize=True)
        print(f"docs/{name} {size[0]}x{size[1]}")
