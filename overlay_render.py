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

from PIL import Image, ImageDraw, ImageFont

W, H = 252, 54
R = 20
SS = 4
BAR_COUNT = 9
BAR_W, BAR_GAP = 3, 4
BAR_MIN, BAR_MAX = 4, 26

BG_TOP = (24, 29, 36)
BG_BOT = (15, 19, 25)
EDGE = (255, 255, 255, 34)
FG = (233, 238, 244)
ACCENT = (242, 178, 62)
MUTED = (150, 161, 173)
GREEN = (87, 211, 140)
RED = (226, 112, 96)

_font_cache: dict[tuple, object] = {}
_BG: dict[int, Image.Image] = {}


def _font_candidates() -> list[str]:
    if sys.platform == "darwin":
        # SF is variable and renders thin through Pillow. Helvetica is the
        # static face that matches the weight the Windows pill uses.
        return [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/SFNS.ttf",
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


def _background(scale: int) -> Image.Image:
    ss = SS * scale
    w, h, r = W * ss, H * ss, R * ss
    grad = Image.new("RGB", (w, h))
    gd = ImageDraw.Draw(grad)
    for y in range(h):
        t = y / max(1, h - 1)
        gd.line([(0, y), (w, y)], fill=tuple(
            int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3)))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    ImageDraw.Draw(img).rounded_rectangle(
        [0, 0, w - 1, h - 1], radius=r, outline=EDGE, width=max(1, ss // 2))
    return img


def _bar_geo():
    total = BAR_COUNT * BAR_W + (BAR_COUNT - 1) * BAR_GAP
    return W - 20 - total, total


def render(label: str, phase: float, hist, scale: int = 1,
           glass: bool = False) -> Image.Image:
    """One frame. `label` is a state name, or `say:`, `hint:`, `alert:` plus text.

    With `glass` the background is left transparent so the window's own material
    shows through; everything drawn on top is unchanged, so the two paths cannot
    drift in wording or geometry.
    """
    scale = max(1, int(scale))
    if glass:
        img = Image.new("RGBA", (W * SS * scale, H * SS * scale), (0, 0, 0, 0))
    else:
        if scale not in _BG:
            _BG[scale] = _background(scale)
        img = _BG[scale].copy()
    d = ImageDraw.Draw(img)
    ss = SS * scale
    cy = H * ss // 2
    pulse = (math.sin(phase * 3.4) + 1) / 2

    dot_col, text, show_bars, ellipsis = MUTED, "", False, False
    dot_r = 4.0 * ss
    if label == "listening":
        dot_col, text, show_bars = ACCENT, "Listening", True
        dot_r = (4.2 + 1.4 * pulse) * ss
    elif label == "transcribing":
        dot_col, text, ellipsis = MUTED, "Transcribing", True
        dot_r = (4.0 + 0.9 * pulse) * ss
    elif label == "done":
        dot_col, text = GREEN, "Copied"
        dot_r = 4.6 * ss
    elif label == "error":
        dot_col, text = RED, "No speech"
        dot_r = 4.6 * ss
    elif label == "paused":
        dot_col, text = MUTED, "Paused"
        dot_r = 4.6 * ss
    elif label.startswith("alert:"):
        # A dead microphone is not the speaker's fault. Distinct from "No speech".
        dot_col, text = RED, label[6:]
        dot_r = 4.6 * ss
    elif label.startswith("say:"):
        dot_col, text = ACCENT, label[4:]
        dot_r = 4.6 * ss
    elif label.startswith("hint:"):
        dot_col, text = ACCENT, label[5:]
        dot_r = 4.6 * ss

    if show_bars and not ellipsis:
        halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
        hd = ImageDraw.Draw(halo)
        hr = dot_r * 2.2
        hd.ellipse([17 * ss - hr, cy - hr, 17 * ss + hr, cy + hr],
                   fill=(dot_col[0], dot_col[1], dot_col[2], 40))
        img.alpha_composite(halo)
    d.ellipse([17 * ss - dot_r, cy - dot_r, 17 * ss + dot_r, cy + dot_r],
              fill=dot_col)

    if text:
        d.text((32 * ss, cy), text, font=_font(15 * ss), fill=FG, anchor="lm")

    if ellipsis:
        x0, _ = _bar_geo()
        for i in range(3):
            k = (phase * 2.2 - i * 0.45) % 3.0
            alpha = int(60 + 180 * max(0.0, math.cos((k - 1.5) * 1.6)))
            x = (x0 + 6 + i * 12) * ss
            d.ellipse([x - 3 * ss, cy - 3 * ss, x + 3 * ss, cy + 3 * ss],
                      fill=(MUTED[0], MUTED[1], MUTED[2], alpha))
    elif show_bars:
        x0, _ = _bar_geo()
        for i, lvl in enumerate(hist):
            hgt = (BAR_MIN + lvl * (BAR_MAX - BAR_MIN)) * ss
            x = (x0 + i * (BAR_W + BAR_GAP)) * ss
            d.rounded_rectangle([x, cy - hgt / 2, x + BAR_W * ss, cy + hgt / 2],
                                radius=BAR_W * ss / 2, fill=ACCENT)

    return img.resize((W * scale, H * scale), _resample())
