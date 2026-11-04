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
    NSBackingStoreBuffered,
    NSBitmapImageRep,
    NSColor,
    NSEvent,
    NSImage,
    NSImageView,
    NSMakeRect,
    NSScreen,
    NSStatusWindowLevel,
    NSTimer,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorIgnoresCycle,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
)
from Foundation import NSObject
from PyObjCTools import AppHelper

from overlay_render import H, W, render

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

    def __init__(self, log=None) -> None:
        self._log = log or (lambda m: None)
        self._label = "hidden"
        self._until = 0.0
        self._phase = 0.0
        self._hist = [0.0] * _BAR_COUNT
        self._visible = False
        self._window = None
        self._view = None
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
            self._ensure_timer()
            self.tick()
        _on_main(apply)

    def level(self, value: float) -> None:
        def apply() -> None:
            with self._lock:
                self._hist = self._hist[1:] + [float(value)]
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
            frame = render(label, self._phase, hist, scale=scale)
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
