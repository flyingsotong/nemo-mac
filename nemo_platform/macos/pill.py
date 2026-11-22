"""The listening pill as an NSWindow.

Same pixels as Windows (overlay_render.render). AppKit does the per-pixel alpha
natively, so the hard part is placement and z-order, not the blit. The window
never activates the app: if it did, the paste would land in Nemo.
"""
from __future__ import annotations

import io
import threading
import time

from AppKit import (
    NSApplication,
    NSAppearance,
    NSAppearanceNameAqua,
    NSAppearanceNameDarkAqua,
    NSColor,
    NSDeviceRGBColorSpace,
    NSGlassEffectView,
    NSGlassEffectViewStyleClear,
    NSGlassEffectViewStyleRegular,
    NSBackingStoreBuffered,
    NSBitmapImageRep,
    NSEvent,
    NSImage,
    NSImageView,
    NSMakeRect,
    NSScreen,
    NSStatusWindowLevel,
    NSTimer,
    NSWorkspace,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorIgnoresCycle,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
)
from Foundation import NSObject
from PyObjCTools import AppHelper

from overlay_render import H, R, W, render
from nemo_platform.macos.theme import resolve as resolve_theme

_BEHAVIOUR = (
    NSWindowCollectionBehaviorCanJoinAllSpaces
    | NSWindowCollectionBehaviorStationary
    | NSWindowCollectionBehaviorFullScreenAuxiliary
    | NSWindowCollectionBehaviorIgnoresCycle
)
_DWELL = {
    "done": 0.9, "error": 0.9, "paused": 0.9,
}
_BAR_COUNT = 9
_INK_CACHE: dict[tuple, dict] = {}


def _tint_key(label: str) -> str | None:
    """Which state gets a tinted material. Status colour is an allowed use of
    colour on glass; everything else keeps the system's own material."""
    if label == "listening":
        return "orange"
    if label == "done":
        return "green"
    if label == "error" or label.startswith("alert:"):
        return "red"
    return None


_TINT_COLORS = {
    "orange": NSColor.systemOrangeColor,
    "green": NSColor.systemGreenColor,
    "red": NSColor.systemRedColor,
}
# A translucent tint: the glass still shows through, so the pill reads as
# coloured material rather than a flat block of paint.
_TINT_ALPHA = 0.28


def _tint_color(key: str):
    return _TINT_COLORS[key]().colorWithAlphaComponent_(_TINT_ALPHA)


def _luminance(rgb) -> float:
    """Relative luminance, for choosing legible ink on a tinted material."""
    def channel(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ink(rgb) -> tuple[int, int, int]:
    """Black or white, whichever reads against a bright status tint."""
    return (0, 0, 0) if _luminance(rgb) > 0.18 else (255, 255, 255)

# Liquid Glass (macOS 26 and later). The window material is the system's own, so
# this costs nothing in CPU: the renderer simply stops painting a background and
# draws the same content over it. Set False to fall back to the solid pill.
USE_GLASS = True


def _glass_available(enabled: bool = True) -> bool:
    return bool(enabled) and bool(USE_GLASS) and NSGlassEffectView is not None


def _on_main(fn) -> None:
    if threading.current_thread() is threading.main_thread():
        fn()
    else:
        AppHelper.callAfter(fn)


class _Tick(NSObject):
    def initWithOwner_(self, owner):
        self = self.init()
        if self is None:
            return None
        self.owner = owner
        return self

    def tick_(self, timer):
        try:
            self.owner.tick()
        except Exception as exc:
            self.owner._log(f"pill tick error: {exc}")


class PillWindow:
    """Queue-free. state() and level() are safe from any thread."""

    def __init__(self, log=None, glass: bool = True,
                 theme: str = "system") -> None:
        self._glass_enabled = bool(glass)
        self._theme_pref = theme
        self._theme = resolve_theme(theme)
        self._log = log or (lambda m: None)
        self._label = "hidden"
        self._until = 0.0
        self._phase = 0.0
        self._hist = [0.0] * _BAR_COUNT
        self._visible = False
        self._window = None
        self._view = None
        self._glass = None
        self._timer = None
        self._tick = None
        self._lock = threading.Lock()

    def start(self) -> None:
        def build() -> None:
            self._build()
        _on_main(build)

    def state(self, name: str) -> None:
        def apply() -> None:
            with self._lock:
                self._label = name
                if name in _DWELL or name.startswith(("say:", "alert:")):
                    self._until = time.time() + 0.9
                elif name.startswith("hint:"):
                    self._until = time.time() + 4.5
            self._apply_tint(name)
            self._ensure_timer()
            self.tick()
        _on_main(apply)

    def level(self, value: float) -> None:
        def apply() -> None:
            with self._lock:
                self._hist = self._hist[1:] + [float(value)]
        _on_main(apply)

    # -- theme -----------------------------------------------------------
    def _apply_tint(self, label: str) -> None:
        """Tint the whole material for a status, never for decoration.

        Regular glass ignores tintColor on macOS 27; clear glass takes it.
        Plain states go back to regular, which is the more legible material
        over arbitrary content.
        """
        if self._glass is None:
            return
        key = _tint_key(label)
        try:
            self._glass.setStyle_(NSGlassEffectViewStyleClear if key
                                  else NSGlassEffectViewStyleRegular)
            self._glass.setTintColor_(_tint_color(key) if key else None)
        except Exception as exc:
            self._log(f"pill tint failed: {exc}")

    def _high_contrast(self) -> bool:
        try:
            return bool(NSWorkspace.sharedWorkspace()
                        .accessibilityDisplayShouldIncreaseContrast())
        except Exception:
            return False

    def _system_ink(self, label: str = "") -> dict:
        """Live system colours, resolved to RGB for the shared renderer.

        AppKit's dynamic colours carry light/dark and accessibility variants.
        When the material is tinted for a status, the label and bars switch to
        black or white — whichever reads against that bright tint.
        """
        tint = _tint_key(label)
        key = (self._theme, self._high_contrast(), tint)
        if key in _INK_CACHE:
            return _INK_CACHE[key]

        wanted = NSAppearance.appearanceNamed_(
            NSAppearanceNameDarkAqua if self._theme == "dark"
            else NSAppearanceNameAqua)
        previous = NSAppearance.currentAppearance()

        def rgb(color):
            converted = color.colorUsingColorSpaceName_(NSDeviceRGBColorSpace)
            if converted is None:
                return None
            return tuple(int(round(v * 255)) for v in (
                converted.redComponent(), converted.greenComponent(),
                converted.blueComponent()))

        try:
            NSAppearance.setCurrentAppearance_(wanted)
            if tint:
                same = _contrast_ink(rgb(_tint_color(tint)))
                ink = {name: same for name in
                       ("fg", "muted", "accent", "green", "red")}
            else:
                # In Increase Contrast, secondaryLabelColor can lose the
                # separation the muted role needs; labelColor is the safe one.
                muted = (NSColor.labelColor() if key[1]
                         else NSColor.secondaryLabelColor())
                ink = {
                    "fg": rgb(NSColor.labelColor()),
                    "muted": rgb(muted),
                    "accent": rgb(NSColor.systemOrangeColor()),
                    "green": rgb(NSColor.systemGreenColor()),
                    "red": rgb(NSColor.systemRedColor()),
                }
        finally:
            try:
                NSAppearance.setCurrentAppearance_(previous)
            except Exception:
                pass
        _INK_CACHE[key] = ink
        return ink

    def set_theme(self, preference: str) -> None:
        """Settings changed the preference; resolve and repaint."""
        self._theme_pref = preference
        self.theme_changed()

    def theme_changed(self) -> None:
        """System appearance changed, or an override was applied."""
        def apply() -> None:
            self._theme = resolve_theme(self._theme_pref)
            self.tick()
        _on_main(apply)

    def _build(self) -> None:
        NSApplication.sharedApplication()
        frame = NSMakeRect(0, 0, W, H)
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False)
        window.setOpaque_(False)
        window.setBackgroundColor_(NSColor.clearColor())
        window.setHasShadow_(False)
        window.setIgnoresMouseEvents_(True)
        window.setLevel_(NSStatusWindowLevel)
        window.setCollectionBehavior_(_BEHAVIOUR)
        window.setHidesOnDeactivate_(False)
        view = NSImageView.alloc().initWithFrame_(frame)
        self._glass = None
        if _glass_available(self._glass_enabled):
            glass = NSGlassEffectView.alloc().initWithFrame_(frame)
            glass.setStyle_(NSGlassEffectViewStyleRegular)
            glass.setCornerRadius_(float(R))
            # No tint: the regular material follows the user's Liquid Glass
            # setting, the backdrop, and the accessibility preferences.
            glass.setContentView_(view)
            window.setContentView_(glass)
            self._glass = glass
            self._apply_tint(self._label)
        else:
            window.setContentView_(view)
        self._window = window
        self._view = view
        self._tick = _Tick.alloc().initWithOwner_(self)

    def _ensure_timer(self) -> None:
        if self._timer is not None or self._tick is None:
            return
        timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / 30.0, self._tick, "tick:", None, True)
        from Foundation import NSRunLoop, NSRunLoopCommonModes
        NSRunLoop.mainRunLoop().addTimer_forMode_(timer, NSRunLoopCommonModes)
        self._timer = timer

    def _stop_timer(self) -> None:
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None

    def tick(self) -> None:
        if self._window is None:
            return
        now = time.time()
        with self._lock:
            label = self._label
            hist = list(self._hist)
            if (label in _DWELL or label.startswith(("say:", "hint:", "alert:"))) and now > self._until:
                label = "hidden"
                self._label = "hidden"
        if label == "hidden":
            if self._visible:
                self._window.orderOut_(None)
                self._visible = False
            self._stop_timer()
            return
        self._phase += 1.0 / 30.0
        if not self._visible:
            self._place()
            self._window.orderFrontRegardless()
            self._visible = True
        try:
            scale = max(1, int(round(self._window.backingScaleFactor() or 2)))
            frame = render(label, self._phase, hist, scale=scale,
                           glass=self._glass is not None, theme=self._theme,
                           ink=self._system_ink(label),
                           contrast=self._high_contrast())
            self._view.setImage_(_nsimage(frame))
        except Exception as exc:
            self._log(f"pill render error: {exc}")

    def _place(self) -> None:
        mouse = NSEvent.mouseLocation()
        screen = NSScreen.mainScreen()
        for candidate in NSScreen.screens():
            frame = candidate.frame()
            origin = frame.origin
            size = frame.size
            if (origin.x <= mouse.x < origin.x + size.width
                    and origin.y <= mouse.y < origin.y + size.height):
                screen = candidate
                break
        vis = screen.visibleFrame()
        x = vis.origin.x + (vis.size.width - W) / 2
        # 88 points above the Dock, matching the Windows work-area inset.
        y = vis.origin.y + 88
        self._window.setFrame_display_(NSMakeRect(x, y, W, H), False)


def _nsimage(pil) -> NSImage:
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    data = buf.getvalue()
    from Foundation import NSData
    nsdata = NSData.dataWithBytes_length_(data, len(data))
    image = NSImage.alloc().initWithData_(nsdata)
    if image is not None:
        image.setSize_((W, H))
    return image
