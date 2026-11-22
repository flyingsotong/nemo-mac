"""Shared pill renderer.

Pillow at 4x, BOX downsample. Windows blits the result through a layered window;
macOS hands the same pixels to an NSImageView. One function, so the two builds
cannot drift in size, palette or wording.

`scale` is the backing scale (1 on Windows, 2 on Retina). The image is still
252 x 54 points; the bitmap is that size times scale.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

W, H = 220, 54
R = 20
SS = 4
TEXT_X = 18          # no dot: the label starts at the left inset
BAR_RIGHT = 16       # waveform sits at the right inset
BAR_COUNT = 9
BAR_W, BAR_GAP = 3, 4
BAR_MIN, BAR_MAX = 4, 26


class Palette(NamedTuple):
    """Fallback surface and ink for the painted (non-glass) pill."""

    bg_top: tuple[int, int, int]
    bg_bottom: tuple[int, int, int]
    edge: tuple[int, int, int, int]
    fg: tuple[int, int, int]
    muted: tuple[int, int, int]
    accent: tuple[int, int, int]
    green: tuple[int, int, int]
    red: tuple[int, int, int]


# Glass mode paints no surface at all: NSGlassEffectView supplies the material,
# which adapts to appearance, backdrop, the user's Liquid Glass setting, Reduce
# Transparency and Increase Contrast. These colours are only the solid fallback.
PALETTES = {
    "dark": Palette(
        bg_top=(30, 36, 45), bg_bottom=(15, 19, 25),
        edge=(255, 255, 255, 38),
        fg=(240, 244, 249), muted=(160, 172, 186),
        accent=(247, 183, 76), green=(92, 216, 146), red=(242, 140, 122),
    ),
    "light": Palette(
        bg_top=(255, 255, 255), bg_bottom=(232, 237, 244),
        edge=(32, 44, 62, 36),
        fg=(23, 28, 36), muted=(83, 95, 110),
        accent=(138, 76, 4), green=(12, 112, 68), red=(184, 46, 42),
    ),
}

# Increase Contrast surface for the solid fallback. System colours already have
# accessible variants; a custom colour needs its own.
HC_SURFACES = {
    "dark": ((12, 15, 20), (0, 0, 0), (255, 255, 255, 120)),
    "light": ((255, 255, 255), (238, 242, 247), (12, 18, 28, 110)),
}

# The doc-image scripts still import these names. Keep them pointing at the
# dark palette so regenerated screenshots match the app's dark theme.
FG = PALETTES["dark"].fg
ACCENT = PALETTES["dark"].accent
MUTED = PALETTES["dark"].muted
BG_BOT = PALETTES["dark"].bg_bottom

_font_cache: dict[tuple, object] = {}
_BG: dict[tuple, Image.Image] = {}


def _font_candidates() -> list[str]:
    if sys.platform == "darwin":
        # SF Pro is the system face. It is variable and renders thin at its
        # default axis value, so _font sets the Medium weight explicitly.
        return [
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
        ]
    root = Path("C:/Windows/Fonts")
    return [str(root / name) for name in
            ("bahnschrift.ttf", "seguisb.ttf", "segoeui.ttf", "arial.ttf")]


def _font(px: int):
    key = (px, sys.platform)
    if key in _font_cache:
        return _font_cache[key]
    chosen = ImageFont.load_default()
    for path in _font_candidates():
        if not Path(path).exists():
            continue
        try:
            chosen = ImageFont.truetype(path, px)
            if path.endswith("SFNS.ttf"):
                try:
                    chosen.set_variation_by_name("Medium")
                except Exception:
                    pass
            break
        except Exception:
            continue
    _font_cache[key] = chosen
    return chosen


def _resample():
    try:
        return Image.Resampling.BOX
    except AttributeError:
        return Image.BOX


def _surface(scale: int, theme: str, glass: bool,
             contrast: bool = False) -> Image.Image:
    """The pill's own surface, cached per scale, theme, glass and contrast.

    Glass returns a fully transparent canvas — the system material is the
    surface. Only the solid fallback paints anything here.
    """
    key = (scale, theme, glass, contrast)
    if key in _BG:
        return _BG[key]
    p = PALETTES.get(theme, PALETTES["dark"])
    ss = SS * scale
    w, h, r = W * ss, H * ss, R * ss
    if glass:
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    else:
        top, bottom, edge = HC_SURFACES[theme] if contrast else (
            p.bg_top, p.bg_bottom, p.edge)
        grad = Image.new("RGB", (w, h))
        gd = ImageDraw.Draw(grad)
        for y in range(h):
            t = y / max(1, h - 1)
            gd.line([(0, y), (w, y)], fill=tuple(
                int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, w - 1, h - 1], radius=r, fill=255)
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        img.paste(grad, (0, 0), mask)
        ImageDraw.Draw(img).rounded_rectangle(
            [0, 0, w - 1, h - 1], radius=r, outline=edge, width=max(1, ss // 2))
    _BG[key] = img
    return img


def _bar_geo():
    total = BAR_COUNT * BAR_W + (BAR_COUNT - 1) * BAR_GAP
    return W - BAR_RIGHT - total, total


def render(label: str, phase: float, hist, scale: int = 1,
           glass: bool = False, theme: str = "dark", ink: dict | None = None,
           contrast: bool = False) -> Image.Image:
    """One frame. `label` is a state name, or `say:`, `hint:`, `alert:` plus text.

    `theme` picks the solid fallback surface; glass paints no surface and lets
    NSGlassEffectView supply one. `ink` lets the Mac pass in live system colours
    so text and status follow appearance, accent and accessibility settings.
    Wording and geometry are identical across modes.
    """
    scale = max(1, int(scale))
    p = PALETTES.get(theme, PALETTES["dark"])
    colors = {name: (ink or {}).get(name, getattr(p, name))
              for name in ("fg", "muted", "accent", "green", "red")}
    img = _surface(scale, theme, glass, contrast).copy()
    d = ImageDraw.Draw(img)
    ss = SS * scale
    cy = H * ss // 2

    text, show_bars, ellipsis = "", False, False
    if label == "listening":
        text, show_bars = "Listening", True
    elif label == "transcribing":
        text, ellipsis = "Transcribing", True
    elif label == "done":
        text = "Copied"
    elif label == "error":
        text = "No speech"
    elif label == "paused":
        text = "Paused"
    elif label.startswith("alert:"):
        # A dead microphone is not the speaker's fault. Distinct from "No speech".
        text = label[6:]
    elif label.startswith("say:"):
        text = label[4:]
    elif label.startswith("hint:"):
        text = label[5:]

    # The waveform owns the right side while it is running; every other state
    # can use the full width for its label.
    if text:
        d.text((TEXT_X * ss, cy), text, font=_font(15 * ss),
               fill=colors["fg"], anchor="lm")

    if ellipsis:
        x0, _ = _bar_geo()
        for i in range(3):
            k = (phase * 2.2 - i * 0.45) % 3.0
            alpha = int(60 + 180 * max(0.0, math.cos((k - 1.5) * 1.6)))
            x = (x0 + 6 + i * 12) * ss
            d.ellipse([x - 3 * ss, cy - 3 * ss, x + 3 * ss, cy + 3 * ss],
                      fill=(colors["muted"][0], colors["muted"][1],
                            colors["muted"][2], alpha))
    elif show_bars:
        x0, _ = _bar_geo()
        for i, lvl in enumerate(hist):
            hgt = (BAR_MIN + lvl * (BAR_MAX - BAR_MIN)) * ss
            x = (x0 + i * (BAR_W + BAR_GAP)) * ss
            d.rounded_rectangle([x, cy - hgt / 2, x + BAR_W * ss, cy + hgt / 2],
                                radius=BAR_W * ss / 2, fill=colors["accent"])

    return img.resize((W * scale, H * scale), _resample())
