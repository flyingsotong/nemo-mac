"""Laptop costs the Windows build never had: battery, heat, App Nap, wake."""
from __future__ import annotations

import subprocess

# NSActivityUserInitiated without NSActivityIdleSystemSleepDisabled.
# Lets the machine sleep, but stops App Nap throttling our timers and the tap.
_USER_INITIATED_ALLOWING_IDLE_SLEEP = 0x00EFFFFF
_THERMAL_SERIOUS = 2

_activity = None


def begin_activity() -> None:
    """Hold for the life of the process. Without this, keep-warm fires late."""
    global _activity
    try:
        from Foundation import NSProcessInfo
        _activity = NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
            _USER_INITIATED_ALLOWING_IDLE_SLEEP, "Nemo dictation")
    except Exception:
        _activity = None


def constrained() -> bool:
    """Battery, Low Power Mode, or serious thermal pressure.

    Keep-warm is a GPU wake for nobody. On a laptop that has to be rarer than
    the desktop interval.
    """
    if _on_battery() or _low_power() or _thermal():
        return True
    return False


def _on_battery() -> bool:
    try:
        out = subprocess.check_output(["pmset", "-g", "batt"], text=True, timeout=2)
    except Exception:
        return False
    return "Battery Power" in out


def _low_power() -> bool:
    try:
        from Foundation import NSProcessInfo
        return bool(NSProcessInfo.processInfo().isLowPowerModeEnabled())
    except Exception:
        return False


def _thermal() -> bool:
    try:
        from Foundation import NSProcessInfo
        return int(NSProcessInfo.processInfo().thermalState()) >= _THERMAL_SERIOUS
    except Exception:
        return False


def watch_wake(callback):
    """Subscribe to lid-open. The observer must be kept alive by the caller."""
    from Foundation import NSObject, NSWorkspace

    class _Wake(NSObject):
        def initWithCallback_(self, fn):
            self = self.init()
            if self is None:
                return None
            self.fn = fn
            return self

        def wake_(self, note):
            try:
                self.fn()
            except Exception:
                pass

    observer = _Wake.alloc().initWithCallback_(callback)
    NSWorkspace.sharedWorkspace().notificationCenter().addObserver_selector_name_object_(
        observer, "wake:", "NSWorkspaceDidWakeNotification", None)
    return observer


def set_interactive_qos() -> None:
    """The default class lets the scheduler treat a dictation as background work."""
    try:
        import ctypes
        lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        # QOS_CLASS_USER_INTERACTIVE = 0x21
        lib.pthread_set_qos_class_self_np(0x21, 0)
    except Exception:
        pass
