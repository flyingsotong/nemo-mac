"""Clipboard and Command-V.

The paste chord is Command, not Control. Every Mac target wants it, including
Terminal. We poll the pasteboard until it holds the text instead of sleeping a
flat 50 ms — that sleep was the largest fixed cost on Windows, and it was padding.
"""
from __future__ import annotations

import time

from AppKit import NSPasteboard, NSPasteboardTypeString
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventPost,
    CGEventSetFlags,
    CGEventSourceCreate,
    kCGEventFlagMaskCommand,
    kCGEventSourceStateHIDSystemState,
    kCGHIDEventTap,
)

_V_KEYCODE = 9  # ANSI V. The Command flag, not the key layout, is what matters.


def copy_text(text: str) -> bool:
    try:
        board = NSPasteboard.generalPasteboard()
        board.clearContents()
        return bool(board.setString_forType_(text, NSPasteboardTypeString))
    except Exception:
        return False


def _holds(text: str) -> bool:
    try:
        board = NSPasteboard.generalPasteboard()
        return board.stringForType_(NSPasteboardTypeString) == text
    except Exception:
        return False


def paste_text(text: str) -> bool:
    """Write the pasteboard, wait until it actually holds the text, post Command-V.

    Does not restore the previous clipboard. Restoring races with slow paste
    targets. Known behaviour, documented rather than papered over.
    """
    if not copy_text(text):
        return False
    for _ in range(20):  # ~100 ms cap
        if _holds(text):
            break
        time.sleep(0.005)
    _post_command_v()
    return True


def _post_command_v() -> None:
    source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
    down = CGEventCreateKeyboardEvent(source, _V_KEYCODE, True)
    up = CGEventCreateKeyboardEvent(source, _V_KEYCODE, False)
    CGEventSetFlags(down, kCGEventFlagMaskCommand)
    CGEventSetFlags(up, kCGEventFlagMaskCommand)
    CGEventPost(kCGHIDEventTap, down)
    CGEventPost(kCGHIDEventTap, up)
