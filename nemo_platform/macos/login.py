"""Start at login via a LaunchAgent. The registry key has no Mac equivalent.

ProcessType Interactive so launchd does not treat the engine as background work
the moment the user is waiting on it.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

from nemo_platform.macos.paths import app_bundle

LABEL = "sg.fractals.nemo"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _uid() -> str:
    return str(os.getuid())


def _domain() -> str:
    return f"gui/{_uid()}"


def startup_get():
    if not PLIST.exists():
        return None
    return str(PLIST)


def startup_set(on: bool) -> tuple[bool, str]:
    if on:
        bundle = app_bundle()
        if bundle is None:
            return False, "not enabling: build Nemo.app first (./build.sh)"
        exe = bundle / "Contents" / "MacOS" / "Nemo"
        if not exe.exists():
            return False, f"not enabling: {exe} does not exist"
        PLIST.parent.mkdir(parents=True, exist_ok=True)
        PLIST.write_text(_plist(exe), encoding="utf-8")
        _bootout()
        try:
            subprocess.run(
                ["launchctl", "bootstrap", _domain(), str(PLIST)],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as exc:
            return False, f"launchctl bootstrap failed: {exc.stderr.strip() or exc}"
        return True, f"enabled: {exe} at login"
    if not PLIST.exists():
        return True, "was not enabled; nothing to remove"
    _bootout()
    try:
        PLIST.unlink()
    except OSError as exc:
        return False, f"could not remove {PLIST}: {exc}"
    return True, "disabled"


def _bootout() -> None:
    subprocess.run(
        ["launchctl", "bootout", f"{_domain()}/{LABEL}"],
        capture_output=True, text=True,
    )


def _plist(exe: Path) -> str:
    path = escape(str(exe))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{path}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>ProcessType</key>
  <string>Interactive</string>
</dict>
</plist>
"""
