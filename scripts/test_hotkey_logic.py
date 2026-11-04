"""Check what the tap decides to do with a modifier event, without a keyboard.

The swallow decision is the product's central promise: while Nemo is running, the
hotkey must never reach the document; while paused, it must. That decision is
`_dispatch`'s return value — None means swallow, the event means pass through.

Run:  .venv/bin/python scripts/test_hotkey_logic.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import Quartz  # noqa: E402

from nemo_platform.macos.hotkey import (  # noqa: E402
    DEFAULT_HOTKEY, HOTKEYS, ESCAPE, TapListener,
)

ALT = Quartz.kCGEventFlagMaskAlternate
CMD = Quartz.kCGEventFlagMaskCommand


def flags_changed(keycode: int, flags: int):
    event = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
    Quartz.CGEventSetType(event, Quartz.kCGEventFlagsChanged)
    Quartz.CGEventSetFlags(event, flags)
    return event


def listener(paused: bool, suppress: bool = True, recording: bool = False,
             hotkey: str = DEFAULT_HOTKEY) -> TapListener:
    return TapListener(
        on_press=lambda: None, on_release=lambda: None, on_escape=lambda: None,
        on_paused_press=lambda: None, is_paused=lambda: paused,
        is_recording=lambda: recording, suppress=suppress, log=lambda m: None,
        hotkey=hotkey,
    )


def main() -> int:
    failures = []

    def check(name: str, passed: bool) -> None:
        print(("PASS  " if passed else "FAIL  ") + name)
        if not passed:
            failures.append(name)

    for name, (right_kc, left_kc, right_bit, left_bit, mask) in HOTKEYS.items():
        label = name.replace("_", " ")
        down = flags_changed(right_kc, mask | right_bit)
        up = flags_changed(right_kc, 0)
        left = flags_changed(left_kc, mask | left_bit)

        live = listener(paused=False, hotkey=name)
        check(f"{label}: press is swallowed",
              live._dispatch(Quartz.kCGEventFlagsChanged, down) is None)
        check(f"{label}: release is swallowed",
              live._dispatch(Quartz.kCGEventFlagsChanged, up) is None)

        paused = listener(paused=True, hotkey=name)
        check(f"{label}: press reaches the app while paused",
              paused._dispatch(Quartz.kCGEventFlagsChanged, down) is not None)
        check(f"{label}: release reaches the app while paused",
              paused._dispatch(Quartz.kCGEventFlagsChanged, up) is not None)

        unsuppressed = listener(paused=False, suppress=False, hotkey=name)
        check(f"{label}: SUPPRESS_HOTKEY=false passes through",
              unsuppressed._dispatch(Quartz.kCGEventFlagsChanged, down) is not None)

        # The opposite-hand key is never the hotkey and must not be swallowed, or
        # ordinary shortcuts and accents break.
        check(f"{label}: the left-hand key is never swallowed",
              live._dispatch(Quartz.kCGEventFlagsChanged, left) is not None)

    # Right Command and Right Option must not be confused for one another.
    cmd = listener(paused=False, hotkey="right_command")
    opt_kc, _, opt_bit, _, opt_mask = HOTKEYS["right_option"]
    check("right Option is not treated as right Command",
          cmd._dispatch(Quartz.kCGEventFlagsChanged,
                        flags_changed(opt_kc, opt_mask | opt_bit)) is not None)

    live = listener(paused=False)
    escape = Quartz.CGEventCreateKeyboardEvent(None, ESCAPE, True)
    check("Escape is observed but passed through",
          live._dispatch(Quartz.kCGEventKeyDown, escape) is not None)

    print()
    print(f"{len(failures)} failure(s)" if failures else "all decisions correct")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
