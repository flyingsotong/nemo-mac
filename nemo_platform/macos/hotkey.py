"""The push-to-talk key, swallowed, via a session event tap.

The key is a modifier, so the press and the release arrive as flagsChanged, not
keyDown. Left and right are distinguished by key code (58/61 for Option, 55/54 for
Command on an ANSI keyboard) and by the device-dependent flag bits; the spec warns
that either mechanism may be the reliable one on a given keyboard, so both are
consulted. Work never happens inside the callback: a slow tap is disabled by the
system, which is the "hotkey died until restart" bug.
"""
from __future__ import annotations

import threading
from typing import Callable

import Quartz

ESCAPE = 53

# name -> (right keycode, left keycode, right device bit, left device bit, modifier mask)
# The device bits are NX_DEVICER*KEYMASK. The standard modifier mask cannot tell
# left from right; these can, and the key code is the cleaner test.
HOTKEYS = {
    "right_command": (54, 55, 0x00000010, 0x00000008, 0x00100000),
    "right_option": (61, 58, 0x00000040, 0x00000020, 0x00080000),
}
DEFAULT_HOTKEY = "right_command"

_DISABLED = {
    int(getattr(Quartz, "kCGEventTapDisabledByTimeout", 0xFFFFFFFE)) & 0xFFFFFFFF,
    int(getattr(Quartz, "kCGEventTapDisabledByUserInput", 0xFFFFFFFF)) & 0xFFFFFFFF,
}


def spec(name: str):
    """Resolve a configured hotkey name, falling back rather than crashing."""
    return HOTKEYS.get(str(name or "").strip().lower(), HOTKEYS[DEFAULT_HOTKEY])


def _keycode(event) -> int:
    return int(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode))


def _flags(event) -> int:
    return int(Quartz.CGEventGetFlags(event))


class TapListener:
    """Same shape as the pynput listener the Windows path returns: start, stop, join."""

    def __init__(self, on_press: Callable[[], None], on_release: Callable[[], None],
                 on_escape: Callable[[], None], on_paused_press: Callable[[], None],
                 is_paused: Callable[[], bool], is_recording: Callable[[], bool],
                 suppress: bool, log: Callable[[str], None],
                 hotkey: str = DEFAULT_HOTKEY) -> None:
        self._on_press = on_press
        self._on_release = on_release
        self._on_escape = on_escape
        self._on_paused_press = on_paused_press
        self._is_paused = is_paused
        self._is_recording = is_recording
        self._suppress = suppress
        self._log = log
        self._right_kc, self._left_kc, self._right_bit, self._left_bit, self._mask = spec(hotkey)
        self._hotkey = hotkey
        self._down = False
        self._seen_modifier = False
        self._tap = None
        self._loop = None
        self._source = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self.failed = False
        self.failure = ""
        # Keep the callback alive. If it is collected, the tap dies silently.
        self._callback = self._handle

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="nemo-tap", daemon=True)
        self._thread.start()
        self._ready.wait(3.0)

    def stop(self) -> None:
        loop = self._loop
        if loop is not None:
            try:
                Quartz.CFRunLoopStop(loop)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def reenable(self) -> None:
        if self._tap is not None:
            try:
                Quartz.CGEventTapEnable(self._tap, True)
                self._log("wake: event tap re-enabled")
            except Exception as exc:
                self._log(f"wake: could not re-enable tap: {exc}")

    def _spawn(self, fn: Callable[[], None]) -> None:
        threading.Thread(target=fn, daemon=True).start()

    def _handle(self, proxy, event_type, event, refcon):
        etype = int(event_type) & 0xFFFFFFFF
        if etype in _DISABLED:
            if self._tap is not None:
                Quartz.CGEventTapEnable(self._tap, True)
            self._log("event tap was disabled; re-enabled")
            return event
        try:
            return self._dispatch(int(event_type), event)
        except Exception as exc:
            self._log(f"hotkey callback error: {exc}")
            return event

    def _dispatch(self, event_type: int, event):
        if event_type == Quartz.kCGEventKeyDown and _keycode(event) == ESCAPE:
            # Observed, never swallowed. Secure-input fields never reach us, which
            # is the correct behaviour, not a bug to fight.
            if self._is_recording():
                self._spawn(self._on_escape)
            return event

        if event_type != Quartz.kCGEventFlagsChanged:
            return event
        kc = _keycode(event)
        flags = _flags(event)
        if not self._seen_modifier:
            # One line, once, so a "hotkey does nothing" report carries its own
            # diagnosis: which key code, and whether the device-specific right-key
            # bit is present on this keyboard.
            self._seen_modifier = True
            self._log(f"modifier event: keycode={kc} flags=0x{flags:08x} "
                      f"devR={'yes' if flags & self._right_bit else 'no'}")
        # Identify the key by code, and accept the device bit as a second opinion:
        # Section 8.2 of the build spec warns that either may be the reliable one
        # on a given keyboard, and the two agree on an ANSI layout.
        if kc == self._right_kc:
            now_down = bool(flags & self._right_bit)
            if (not now_down and not (flags & self._left_bit)
                    and (flags & self._mask)):
                now_down = True     # device bit absent; the key code told us
        elif kc == self._left_kc and (flags & self._right_bit):
            now_down = True         # bits say the right-hand key, code says left
        elif kc == self._left_kc and self._down:
            now_down = False        # the release for that odd case; must clear the latch
        else:
            return event

        if self._is_paused():
            if now_down and not self._down:
                self._down = True
                self._spawn(self._on_paused_press)
            elif not now_down:
                self._down = False
            return event  # paused hands the key back to the system

        if now_down and not self._down:
            self._down = True
            self._spawn(self._on_press)
        elif not now_down and self._down:
            self._down = False
            self._spawn(self._on_release)
        if self._suppress:
            return None
        return event

    def _run(self) -> None:
        mask = (
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
            | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
            | Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
        )
        try:
            tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap,
                Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionDefault,
                mask,
                self._callback,
                None,
            )
        except Exception as exc:
            self.failed = True
            self.failure = f"CGEventTapCreate raised: {exc}"
            self._log(self.failure)
            self._ready.set()
            return
        if tap is None:
            self.failed = True
            self.failure = (
                "event tap was not created. Grant Accessibility (and Input "
                "Monitoring, if listed) to the app that is running Nemo, then relaunch."
            )
            self._log(self.failure)
            self._ready.set()
            return
        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(loop, source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        self._tap = tap
        self._source = source
        self._loop = loop
        self._log(f"event tap installed ({self._hotkey.replace('_', ' ').title()})")
        self._ready.set()
        Quartz.CFRunLoopRun()
        self._log("event tap stopped")


def install(app, suppress: bool, push: bool, log, hotkey: str = DEFAULT_HOTKEY) -> TapListener:
    """Wire the tap to the app. Push-to-talk is the default; toggle is the option."""

    def on_press() -> None:
        from nemo_platform.macos.power import set_interactive_qos
        set_interactive_qos()
        if push:
            app.press()
        else:
            app.toggle()

    def on_release() -> None:
        if push:
            app.release()

    listener = TapListener(
        on_press=on_press,
        on_release=on_release,
        on_escape=app.cancel,
        on_paused_press=lambda: app._state("paused"),
        is_paused=lambda: app.paused,
        is_recording=lambda: app.recorder.active,
        suppress=suppress,
        log=log,
        hotkey=hotkey,
    )
    listener.start()
    return listener
