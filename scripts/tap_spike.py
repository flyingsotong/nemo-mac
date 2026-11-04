"""Prove the tap before building a UI on top of it.

Run:  .venv/bin/python scripts/tap_spike.py [seconds]

Prints whether the tap was created, then logs every event that reaches it:
key code, flags, and whether it was swallowed. Hold Right Option to see it.
Needs Accessibility for the process that runs it.
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from nemo_platform.macos.hotkey import TapListener  # noqa: E402
from nemo_platform.macos.permissions import accessibility_trusted, running_identity  # noqa: E402

COUNT = {"press": 0, "release": 0, "escape": 0}


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    print("running identity:", running_identity())
    print("accessibility trusted:", accessibility_trusted(prompt=True))
    listener = TapListener(
        on_press=lambda: _hit("press"),
        on_release=lambda: _hit("release"),
        on_escape=lambda: _hit("escape"),
        on_paused_press=lambda: None,
        is_paused=lambda: False,
        is_recording=lambda: False,
        suppress=True,
        log=lambda m: print(f"[tap] {m}", flush=True),
    )
    listener.start()
    if listener.failed:
        print("FAILED:", listener.failure)
        return 2
    print(f"tap live for {seconds:.0f}s — hold Right Option, then press Escape")
    time.sleep(seconds)
    listener.stop()
    print("events:", COUNT)
    return 0 if COUNT["press"] and COUNT["release"] else 1


def _hit(name: str) -> None:
    COUNT[name] += 1
    print(f"  {name} #{COUNT[name]}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
