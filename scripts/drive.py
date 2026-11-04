"""Drive a full press/release through the running app with synthetic Option events.

The tap and the recorder are real; only the keystroke is synthetic. Used to prove
the loop and the failure paths without needing someone to hold a key.

Run:  .venv/bin/python scripts/drive.py 2.0
"""
from __future__ import annotations

import subprocess
import sys
import time

from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventPost,
    CGEventSetFlags,
    CGEventSetType,
    CGEventSourceCreate,
    kCGEventFlagMaskAlternate,
    kCGEventFlagsChanged,
    kCGEventSourceStateHIDSystemState,
    kCGHIDEventTap,
)

RIGHT_OPTION = 61


def option(down: bool) -> None:
    src = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
    ev = CGEventCreateKeyboardEvent(src, RIGHT_OPTION, down)
    CGEventSetType(ev, kCGEventFlagsChanged)
    CGEventSetFlags(ev, (kCGEventFlagMaskAlternate | 0x40) if down else 0)
    CGEventPost(kCGHIDEventTap, ev)


def main() -> int:
    hold = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    time.sleep(0.3)
    option(True)
    time.sleep(hold)
    subprocess.run(["screencapture", "-x", "/tmp/drive-listening.png"], check=False)
    option(False)
    time.sleep(1.2)
    subprocess.run(["screencapture", "-x", "/tmp/drive-after.png"], check=False)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
