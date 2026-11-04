"""TCC checks. Windows had nothing to check; here this is the first thing that fails."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def accessibility_trusted(prompt: bool = False) -> bool:
    try:
        import ApplicationServices
    except Exception:
        return False
    try:
        if prompt:
            opts = {"AXTrustedCheckOptionPrompt": True}
            return bool(ApplicationServices.AXIsProcessTrustedWithOptions(opts))
        return bool(ApplicationServices.AXIsProcessTrusted())
    except Exception:
        return False


def microphone_status() -> str:
    """authorized, denied, restricted, not_determined, or unknown."""
    try:
        import AVFoundation
        status = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(
            AVFoundation.AVMediaTypeAudio)
    except Exception:
        return "unknown"
    return {
        0: "not_determined",
        1: "restricted",
        2: "denied",
        3: "authorized",
    }.get(int(status), "unknown")


def request_microphone() -> None:
    """Ask once. A missing NSMicrophoneUsageDescription kills a bundled app instead."""
    try:
        import AVFoundation
    except Exception:
        return
    if microphone_status() != "not_determined":
        return
    done = __import__("threading").Event()

    def handler(granted):
        done.set()

    AVFoundation.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
        AVFoundation.AVMediaTypeAudio, handler)
    done.wait(30)


def missing() -> list[str]:
    out = []
    if not accessibility_trusted(prompt=False):
        out.append("Accessibility")
    mic = microphone_status()
    if mic not in ("authorized", "unknown"):
        out.append("Microphone")
    return out


def open_settings(which: str) -> None:
    """which is Accessibility or Microphone. Classic URL; macOS redirects it."""
    pane = "Privacy_Microphone" if which == "Microphone" else "Privacy_Accessibility"
    url = f"x-apple.systempreferences:com.apple.preference.security?{pane}"
    try:
        subprocess.run(["open", url], check=False)
    except Exception:
        pass


def running_identity() -> str:
    """The thing the user has to tick. A source run is the Python binary, not Nemo."""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve().parents[2])
    return str(Path(sys.executable).resolve())
