"""Show the pill in a given state, capture the screen, exit.

Run:  .venv/bin/python scripts/pill_shot.py "hint:Hold Right Option to talk" /tmp/pill.png
Needs Screen Recording for the process, or the capture is a blank image.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from AppKit import NSApplication, NSApplicationActivationPolicyAccessory  # noqa: E402
from PyObjCTools import AppHelper  # noqa: E402

from nemo_platform.macos.pill import PillWindow  # noqa: E402


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "hint:Hold Right Option to talk"
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/pill.png")
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    pill = PillWindow(log=lambda m: print(m, flush=True))
    pill.start()
    pill.state(label)

    def shot() -> None:
        subprocess.run(["screencapture", "-x", str(out)], check=False)
        print(f"captured {out}", flush=True)

    AppHelper.callLater(1.2, shot)
    AppHelper.callLater(1.8, AppHelper.stopEventLoop)
    AppHelper.runEventLoop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
