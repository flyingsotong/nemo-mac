"""Check what the tap decides to do with a modifier event, without a keyboard.

The swallow decision is the product's central promise: while Nemo is running,
Right Option must never reach the document; while paused, it must. That decision
is `_dispatch`'s return value — None means swallow, the event means pass through.

Run:  .venv/bin/python scripts/test_hotkey_logic.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import Quartz  # noqa: E402

from nemo_platform.macos.hotkey import LEFT_OPTION, RIGHT_OPTION, TapListener  # noqa: E402

DEV_LALT = 0x00000020
DEV_RALT = 0x00000040
ALT = Quartz.kCGEventFlagMaskAlternate


def make_flags_changed(keycode: int, flags: int):
    event = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
    Quartz.CGEventSetType(event, Quartz.kCGEventFlagsChanged)
    Quartz.CGEventSetFlags(event, flags)
    return event


def listener(paused: bool, suppress: bool = True, recording: bool = False) -> TapListener:
    return TapListener(
        on_press=lambda: None, on_release=lambda: None, on_escape=lambda: None,
        on_paused_press=lambda: None, is_paused=lambda: paused,
        is_recording=lambda: recording, suppress=suppress, log=lambda m: None,
    )


def main() -> int:
    failures = []

    def check(name: str, passed: bool) -> None:
        print(("PASS  " if passed else "FAIL  ") + name)
        if not passed:
            failures.append(name)

    right_down = make_flags_changed(RIGHT_OPTION, ALT | DEV_RALT)
    right_up = make_flags_changed(RIGHT_OPTION, 0)
    left_down = make_flags_changed(LEFT_OPTION, ALT | DEV_LALT)

    live = listener(paused=False)
    check("running: right Option press is swallowed",
          live._dispatch(Quartz.kCGEventFlagsChanged, right_down) is None)
    check("running: right Option release is swallowed",
          live._dispatch(Quartz.kCGEventFlagsChanged, right_up) is None)

    paused = listener(paused=True)
    check("paused: right Option press reaches the app",
          paused._dispatch(Quartz.kCGEventFlagsChanged, right_down) is not None)
    check("paused: right Option release reaches the app",
          paused._dispatch(Quartz.kCGEventFlagsChanged, right_up) is not None)

    unsuppressed = listener(paused=False, suppress=False)
    check("SUPPRESS_HOTKEY=false: press reaches the app",
          unsuppressed._dispatch(Quartz.kCGEventFlagsChanged, right_down) is not None)

    # Left Option is not the hotkey and must never be swallowed, or typing accents
    # silently breaks.
    check("running: left Option is never swallowed",
          live._dispatch(Quartz.kCGEventFlagsChanged, left_down) is not None)

    escape = Quartz.CGEventCreateKeyboardEvent(None, 53, True)
    check("recording: Escape is observed but passed through",
          live._dispatch(Quartz.kCGEventKeyDown, escape) is not None)

    print()
    print(f"{len(failures)} failure(s)" if failures else "all decisions correct")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
