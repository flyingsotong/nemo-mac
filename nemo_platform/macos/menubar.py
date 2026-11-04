"""Menu bar item. There is no default action: clicking opens the menu.

That removes the Windows trap where a stray left click launched whatever handles
.json. Pause is a menu item. Pressing the hotkey while paused still shows the
pill, which is what stops a paused app from being a mystery.
"""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSImage,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSObject
from PIL import Image, ImageDraw
from PyObjCTools import AppHelper

from nemo_platform.macos.permissions import missing, open_settings, running_identity
from nemo_platform.macos.dialog import explain_permissions


ACCENT = (242, 178, 62)


def _icon(dim: bool = False, colour: tuple | None = None) -> NSImage:
    """22 pt waveform. Monochrome template by default so macOS inverts it in dark
    mode; an explicit colour turns the template off, which is how "listening" is
    signalled on the app's own icon.

    The orange microphone macOS shows while the mic is open is a system privacy
    indicator — no app can hide it, and it should not try. This is the app saying
    the same thing in its own voice.
    """
    img = Image.new("RGBA", (44, 44), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    alpha = 110 if dim else 255
    heights = [10, 18, 28, 16, 34, 16, 28, 18, 10]
    x = 4
    for h in heights:
        y0 = (44 - h) // 2
        fill = (colour[0], colour[1], colour[2], alpha) if colour else (0, 0, 0, alpha)
        draw.rounded_rectangle([x, y0, x + 2, y0 + h], radius=1, fill=fill)
        x += 4
    from Foundation import NSData
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw = buf.getvalue()
    image = NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(raw, len(raw)))
    image.setSize_((22, 22))
    image.setTemplate_(colour is None)
    return image


class _Target(NSObject):
    def initWithOwner_(self, owner):
        self = self.init()
        if self is None:
            return None
        self.owner = owner
        return self

    def pause_(self, sender):
        self.owner._toggle_pause()

    def copy_(self, sender):
        self.owner._copy_last()

    def insert_(self, sender):
        self.owner._insert_last()

    def settings_(self, sender):
        self.owner._open("config.json")

    def vocabulary_(self, sender):
        self.owner._open("vocabulary.txt")

    def reload_(self, sender):
        self.owner._reload()

    def startup_(self, sender):
        self.owner._toggle_startup()

    def permissions_(self, sender):
        self.owner._check_permissions()

    def quit_(self, sender):
        self.owner._quit()

    def menuWillOpen_(self, menu):
        self.owner._refresh(menu)


class MenuBar:
    def __init__(self, *, version: str, root: Path, startup_get, startup_set,
                 on_reload, icon_path: Path, log,
                 on_copy_last=None, on_insert_last=None, last_preview=None,
                 is_paused=None, on_toggle_pause=None, on_say=None,
                 status_lines=None, hotkey_name: str = "Right Command", on_ready=None):
        self.version = version
        self.root = Path(root)
        self.startup_get = startup_get
        self.startup_set = startup_set
        self.on_reload = on_reload
        self.log = log
        self.on_copy_last = on_copy_last
        self.on_insert_last = on_insert_last
        self.last_preview = last_preview
        self.is_paused = is_paused
        self.on_toggle_pause = on_toggle_pause
        self.on_say = on_say
        self.status_lines = status_lines
        self.hotkey_name = hotkey_name
        self.on_ready = on_ready
        self._normal = None
        self._dim = None
        self._accent = None
        self._listening = False
        self._item = None
        self._target = None
        self._items: dict[str, NSMenuItem] = {}

    def run(self) -> None:
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        self._normal = _icon(False)
        self._dim = _icon(True)
        self._accent = _icon(False, colour=ACCENT)
        self._target = _Target.alloc().initWithOwner_(self)
        item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        button = item.button()
        button.setImage_(self._normal)
        button.setToolTip_(f"Nemo {self.version} — hold {self.hotkey_name} to talk")
        menu = self._build_menu()
        # AppKit otherwise re-validates every item against its target and turns
        # Copy/Insert back on when there is no transcript. Our own enable state
        # is the true one.
        menu.setAutoenablesItems_(False)
        menu.setDelegate_(self._target)
        item.setMenu_(menu)
        self._item = item
        self.log("menu bar item installed")
        # Anything that needs a modal must wait for the run loop, or NSAlert
        # returns immediately and the user never sees it.
        if self.on_ready is not None:
            AppHelper.callLater(1.0, self.on_ready)
        AppHelper.runEventLoop()

    def stop(self) -> None:
        try:
            AppHelper.stopEventLoop()
        except Exception:
            pass
        if self._item is not None:
            try:
                NSStatusBar.systemStatusBar().removeStatusItem_(self._item)
            except Exception:
                pass

    def _notify(self, text: str) -> None:
        if self.on_say is not None:
            try:
                self.on_say(text)
            except Exception as exc:
                self.log(f"pill confirm failed: {exc}")

    def _lines(self) -> list[str]:
        if self.status_lines is None:
            return []
        try:
            return list(self.status_lines() or [])
        except Exception:
            return []

    def _paused(self) -> bool:
        if self.is_paused is None:
            return False
        try:
            return bool(self.is_paused())
        except Exception:
            return False

    def _apply_icon(self) -> None:
        """One glance should say which of the three states the app is in."""
        paused = self._paused()
        listening = self._listening and not paused
        button = self._item.button() if self._item is not None else None
        if button is None:
            return
        if listening:
            button.setImage_(self._accent)
            tip = f"Nemo {self.version} — listening"
        elif paused:
            button.setImage_(self._dim)
            tip = f"Nemo {self.version} — paused"
        else:
            button.setImage_(self._normal)
            tip = f"Nemo {self.version} — hold {self.hotkey_name} to talk"
        button.setToolTip_(tip)

    def set_listening(self, active: bool) -> None:
        """Called from the recording thread; the icon itself must change on main."""
        self._listening = bool(active)

        def apply() -> None:
            self._apply_icon()
        if threading.current_thread() is threading.main_thread():
            apply()
        else:
            AppHelper.callAfter(apply)

    def _build_menu(self) -> NSMenu:
        menu = NSMenu.alloc().init()
        self._add(menu, "version", f"Nemo {self.version}", None, enabled=False)
        self._add(menu, "engine", "Engine: starting...", None, enabled=False)
        self._add(menu, "model", "Model", None, enabled=False)
        self._add(menu, "privacy", "Local only: audio never leaves this Mac", None, enabled=False)
        menu.addItem_(NSMenuItem.separatorItem())
        self._add(menu, "pause", "Pause dictation", "pause:")
        self._add(menu, "last", "Last: (nothing yet)", None, enabled=False)
        self._add(menu, "copy", "Copy last transcript", "copy:")
        self._add(menu, "insert", "Insert last transcript", "insert:")
        menu.addItem_(NSMenuItem.separatorItem())
        self._add(menu, "settings", "Open settings", "settings:")
        self._add(menu, "vocab", "Open vocabulary", "vocabulary:")
        self._add(menu, "reload", "Reload settings", "reload:")
        self._add(menu, "startup", "Start at login", "startup:")
        self._add(menu, "perms", "Check permissions", "permissions:")
        menu.addItem_(NSMenuItem.separatorItem())
        self._add(menu, "quit", "Quit Nemo", "quit:")
        return menu

    def _add(self, menu, key, title, action, enabled=True) -> None:
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
        if action:
            item.setTarget_(self._target)
        item.setEnabled_(enabled)
        menu.addItem_(item)
        self._items[key] = item

    def _refresh(self, menu) -> None:
        lines = self._lines()
        for key, index in (("engine", 0), ("model", 1), ("privacy", 2)):
            item = self._items.get(key)
            if item is not None and index < len(lines) and lines[index]:
                item.setTitle_(lines[index])
        last = self._items.get("last")
        if last is not None:
            last.setTitle_(self._last_label())
        copy = self._items.get("copy")
        insert = self._items.get("insert")
        has = self._has_last()
        if copy is not None:
            copy.setEnabled_(has)
        if insert is not None:
            insert.setEnabled_(has)
        pause = self._items.get("pause")
        if pause is not None:
            pause.setState_(1 if self._paused() else 0)
        startup = self._items.get("startup")
        if startup is not None:
            startup.setState_(1 if self.startup_get() else 0)
        self._apply_icon()

    def _last_label(self) -> str:
        text = ""
        if self.last_preview is not None:
            try:
                text = self.last_preview() or ""
            except Exception:
                text = ""
        if not text:
            return "Last: (nothing yet)"
        one = " ".join(text.split())
        shown = one[:34] + "..." if len(one) > 34 else one
        return f'Last: "{shown}"'

    def _has_last(self) -> bool:
        if self.last_preview is None:
            return False
        try:
            return bool(self.last_preview())
        except Exception:
            return False

    def _toggle_pause(self) -> None:
        if self.on_toggle_pause is None:
            return
        try:
            now = bool(self.on_toggle_pause())
        except Exception as exc:
            self.log(f"pause toggle failed: {exc}")
            return
        self._apply_icon()
        self._notify("Paused" if now else "Resumed")

    def _copy_last(self) -> None:
        ok = False
        if self.on_copy_last is not None:
            try:
                ok = bool(self.on_copy_last())
            except Exception as exc:
                self.log(f"copy last failed: {exc}")
        self._notify("Copied" if ok else "Nothing to copy")

    def _insert_last(self) -> None:
        def work() -> None:
            time.sleep(0.05)  # let the menu close so focus returns to the document
            ok = False
            if self.on_insert_last is not None:
                try:
                    ok = bool(self.on_insert_last())
                except Exception as exc:
                    self.log(f"insert last failed: {exc}")
            AppHelper.callAfter(lambda: self._notify("Inserted" if ok else "Nothing to insert"))
        threading.Thread(target=work, daemon=True).start()

    def _open(self, name: str) -> None:
        path = self.root / name
        try:
            if not path.exists():
                if name.endswith(".json"):
                    path.write_text("{}\n", encoding="utf-8")
                else:
                    path.write_text("# one term per line\n", encoding="utf-8")
            subprocess.run(["open", "-t", str(path)], check=False)
        except Exception as exc:
            self.log(f"could not open {path}: {exc}")

    def _reload(self) -> None:
        self._notify("Reloading")

        def work() -> None:
            ok = False
            try:
                ok = bool(self.on_reload())
            except Exception as exc:
                self.log(f"reload failed: {exc}")
            self.log(f"reload settings: {'ok' if ok else 'failed'}")
            AppHelper.callAfter(lambda: self._notify("Reloaded" if ok else "Reload failed"))
        threading.Thread(target=work, daemon=True).start()

    def _toggle_startup(self) -> None:
        enable = not bool(self.startup_get())
        ok, msg = self.startup_set(enable)
        self.log(f"start at login -> {msg}")
        self._notify("Autostart on" if ok and enable else
                     "Autostart off" if ok else "Autostart failed")

    def _check_permissions(self) -> None:
        want = explain_permissions(missing(), running_identity())
        if want:
            open_settings(want)

    def _quit(self) -> None:
        self.log("quit from menu")
        AppHelper.stopEventLoop()
