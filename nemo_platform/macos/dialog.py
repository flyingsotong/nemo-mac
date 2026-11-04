"""NSAlert instead of MessageBoxW. Shown on the app's own terms, not as a toast."""
from __future__ import annotations

from AppKit import NSAlert, NSApp, NSApplicationActivationPolicyRegular


def _alert(title: str, body: str, buttons: list[str]) -> int:
    # An accessory app's modal can appear behind everything. Flip for the
    # duration of the question, then put the Dock icon away again.
    previous = None
    try:
        previous = NSApp.activationPolicy()
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        NSApp.activateIgnoringOtherApps_(True)
    except Exception:
        pass
    alert = NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_(body)
    for label in buttons:
        alert.addButtonWithTitle_(label)
    try:
        return int(alert.runModal())
    finally:
        if previous is not None:
            try:
                NSApp.setActivationPolicy_(previous)
            except Exception:
                pass


def choose_model(want: str, other: str, body: str) -> str | None:
    """1000 is the first button, 1001 the second, anything else is cancel."""
    answer = _alert(
        "Nemo needs a speech model.",
        body,
        [f"Download {want}", f"Download {other}", "Not now"],
    )
    if answer == 1000:
        return want
    if answer == 1001:
        return other
    return None


def explain_permissions(missing: list[str], identity: str) -> str | None:
    if not missing:
        _alert("Permissions", "Accessibility and the microphone are both granted.", ["OK"])
        return None
    which = missing[0]
    body = (
        f"Nemo cannot {'hear you' if which == 'Microphone' else 'see the hotkey'} "
        f"until {which} is granted.\n\n"
        f"Tick the entry for:\n{identity}\n\n"
        "If the hotkey still does nothing after Accessibility, also enable "
        "Input Monitoring for the same app. Dictation into a password field "
        "will not work; macOS blocks every tap there, and that is correct."
    )
    answer = _alert(f"Nemo needs {which}", body, ["Open Settings", "Later"])
    if answer == 1000:
        return which
    return None
