"""Appearance for the Mac build: follow the system, or pin light or dark.

The pill is drawn by Pillow, so it needs the resolved appearance as a plain
string. AppKit windows and menus need an NSAppearance instead. This module is
the one place that knows both, and it watches the system notification so a
switch in Control Centre repaints the pill while it is on screen.
"""
from __future__ import annotations

import objc
from AppKit import (
    NSAppearance,
    NSAppearanceNameAqua,
    NSAppearanceNameDarkAqua,
    NSApplication,
    NSDistributedNotificationCenter,
)
from Foundation import NSObject

SYSTEM = "system"
LIGHT = "light"
DARK = "dark"
VALID = (SYSTEM, LIGHT, DARK)

_theme_notification = "AppleInterfaceThemeChangedNotification"
_observer = None


def normalise(preference: str) -> str:
    """Treat junk from a hand-edited config.json as 'follow the system'."""
    return preference if preference in VALID else SYSTEM


def resolve(preference: str = SYSTEM) -> str:
    """The actual appearance to draw with, never 'system'."""
    preference = normalise(preference)
    if preference != SYSTEM:
        return preference
    appearance = NSApplication.sharedApplication().effectiveAppearance()
    if appearance is not None:
        match = appearance.bestMatchFromAppearancesWithNames_(
            [NSAppearanceNameDarkAqua, NSAppearanceNameAqua])
        if match == NSAppearanceNameDarkAqua:
            return DARK
    return LIGHT


def apply(preference: str = SYSTEM) -> None:
    """Set the app-wide appearance; None hands control back to macOS."""
    preference = normalise(preference)
    app = NSApplication.sharedApplication()
    if preference == LIGHT:
        app.setAppearance_(NSAppearance.appearanceNamed_(NSAppearanceNameAqua))
    elif preference == DARK:
        app.setAppearance_(NSAppearance.appearanceNamed_(NSAppearanceNameDarkAqua))
    else:
        app.setAppearance_(None)


class _ThemeObserver(NSObject):
    def initWithCallback_(self, callback):
        self = objc.super(_ThemeObserver, self).init()
        if self is None:
            return None
        self.callback = callback
        return self

    def interfaceThemeChanged_(self, note):
        try:
            self.callback()
        except Exception:
            pass


def observe(callback) -> None:
    """Call `callback` when macOS switches between light and dark.

    One observer per process; the global keeps it alive for the app's lifetime.
    """
    global _observer
    if _observer is not None:
        return
    observer = _ThemeObserver.alloc().initWithCallback_(callback)
    NSDistributedNotificationCenter.defaultCenter().addObserver_selector_name_object_(
        observer, "interfaceThemeChanged:", _theme_notification, None)
    _observer = observer
