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
    NSView,
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
# Room for the status glow outside the glass. The window is larger than the
# pill so the halo is not clipped; placement still centres the visible pill.
_PAD = 28
_WW, _HH = W + 2 * _PAD, H + 2 * _PAD


def _status_key(label: str) -> str | None:
    """Which state gets a coloured glow. The glass itself is never tinted."""
    if label == "listening":
        return "orange"
    if label == "done":
        return "green"
    if label == "error" or label.startswith("alert:"):
        return "red"
    return None


_GLOW_COLORS = {
    "orange": NSColor.systemOrangeColor,
    "green": NSColor.systemGreenColor,
    "red": NSColor.systemRedColor,
}
_GLOW_RADIUS = 18.0
_GLOW_OPACITY = 0.85

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
            self._apply_glow(name)
            self._ensure_timer()
            self.tick()
        _on_main(apply)

    def level(self, value: float) -> None:
        def apply() -> None:
            with self._lock:
                self._hist = self._hist[1:] + [float(value)]
        _on_main(apply)

    # -- status glow ------------------------------------------------------
    def _apply_glow(self, label: str) -> None:
        """Colour the halo around the glass, leaving the material clear."""
        if self._glass is None:
            return
        layer = self._glass.layer()
        if layer is None:
            return
        key = _status_key(label)
        try:
            self._glass.setTintColor_(None)
            self._glass.setStyle_(NSGlassEffectViewStyleClear if key
                                  else NSGlassEffectViewStyleRegular)
            if key:
                layer.setShadowColor_(_GLOW_COLORS[key]().CGColor())
                layer.setShadowOffset_((0, 0))
                layer.setShadowRadius_(_GLOW_RADIUS)
                layer.setShadowOpacity_(_GLOW_OPACITY)
            else:
                layer.setShadowOpacity_(0)
        except Exception as exc:
            self._log(f"pill glow failed: {exc}")

    def _high_contrast(self) -> bool:
        try:
            return bool(NSWorkspace.sharedWorkspace()
                        .accessibilityDisplayShouldIncreaseContrast())
        except Exception:
            return False

    def _system_ink(self) -> dict:
        """Live system colours, resolved to RGB for the shared renderer.

        The glass is never tinted now — status lives in the surrounding glow —
        so the label keeps the ordinary dynamic system colours in every state.
        """
        key = (self._theme, self._high_contrast())
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
        frame = NSMakeRect(0, 0, _WW, _HH)
        pill_frame = NSMakeRect(_PAD, _PAD, W, H)
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False)
        window.setOpaque_(False)
        window.setBackgroundColor_(NSColor.clearColor())
        window.setHasShadow_(False)
        window.setIgnoresMouseEvents_(True)
        window.setLevel_(NSStatusWindowLevel)
        window.setCollectionBehavior_(_BEHAVIOUR)
        window.setHidesOnDeactivate_(False)
        container = NSView.alloc().initWithFrame_(frame)
        container.setWantsLayer_(True)
        view = NSImageView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
        self._glass = None
        if _glass_available(self._glass_enabled):
            glass = NSGlassEffectView.alloc().initWithFrame_(pill_frame)
            glass.setStyle_(NSGlassEffectViewStyleRegular)
            glass.setCornerRadius_(float(R))
            glass.setWantsLayer_(True)
            # The material stays clear; colour lives in the halo outside it.
            glass.setTintColor_(None)
            glass.setContentView_(view)
            container.addSubview_(glass)
            self._glass = glass
            self._apply_glow(self._label)
        else:
            view.setFrame_(pill_frame)
            container.addSubview_(view)
        window.setContentView_(container)
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
                           ink=self._system_ink(),
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
        # Centre the visible pill; the extra padding only holds the glow.
        x = vis.origin.x + (vis.size.width - W) / 2 - _PAD
        # 88 points above the Dock, matching the Windows work-area inset.
        y = vis.origin.y + 88 - _PAD
        self._window.setFrame_display_(NSMakeRect(x, y, _WW, _HH), False)


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
