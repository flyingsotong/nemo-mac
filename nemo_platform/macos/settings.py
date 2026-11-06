"""The Settings window.

One place for everything that used to be a JSON edit. Values are read from the
running app, written back to config.json, and applied immediately: the engine is
restarted only when a setting actually needs it, and the microphone is reopened
rather than the app being relaunched.

Built with explicit frames rather than Auto Layout on purpose - the window does not
resize, and frames are far easier to reason about from Python than constraints.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import objc
from Foundation import NSObject
from AppKit import (
    NSApplication, NSApplicationActivationPolicyAccessory,
    NSApplicationActivationPolicyRegular, NSBackingStoreBuffered, NSButton,
    NSColor, NSFont, NSMakeRect, NSPopUpButton, NSScrollView, NSTabView,
    NSTabViewItem, NSTextField, NSTextView, NSWindow, NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)

W, H = 600, 470
LABEL_X, CONTROL_X, CONTROL_W = 24, 208, 340
ROW_H = 34


class SettingsWindow(NSObject):
    """Subclasses NSObject because it is its own window delegate."""

    def initWithApp_onApply_log_(self, app, on_apply, log):
        self = objc.super(SettingsWindow, self).init()
        if self is None:
            return None
        self.app = app
        self.on_apply = on_apply
        self.log = log
        self.window = None
        self.controls = {}
        self._vocab = None
        self._audio_status = None
        self._advanced_status = None
        return self

    # -- lifecycle ------------------------------------------------------
    def show(self) -> None:
        if self.window is None:
            self._build()
        self.refresh_values()
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyRegular)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)

    def _build(self) -> None:
        rect = NSMakeRect(0, 0, W, H)
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered, False)
        win.setTitle_("Nemo Settings")
        win.setReleasedWhenClosed_(False)
        win.setDelegate_(self)
        win.center()

        tabs = NSTabView.alloc().initWithFrame_(NSMakeRect(12, 12, W - 24, H - 24))
        win.setContentView_(tabs)
        self.tabs = tabs
        for title in ("General", "Audio", "Transcription", "Advanced"):
            item = NSTabViewItem.alloc().initWithIdentifier_(title)
            item.setLabel_(title)
            view = self.make_view()
            self.tabs.addTabViewItem_(item)
            item.setView_(view)
            self.fill_tab(title, view)
        self.window = win

    def make_view(self):
        from AppKit import NSView
        return NSView.alloc().initWithFrame_(NSMakeRect(0, 0, W - 28, H - 70))

    # -- small builders -------------------------------------------------
    def make_label(self, view, text: str, y: int, bold: bool = False):
        field = NSTextField.labelWithString_(text)
        field.setFrame_(NSMakeRect(LABEL_X, y, CONTROL_X - LABEL_X - 12, 20))
        field.setFont_(NSFont.systemFontOfSize_(13))
        if bold:
            field.setFont_(NSFont.boldSystemFontOfSize_(13))
        view.addSubview_(field)
        return field

    def make_note(self, view, text: str, y: int):
        field = NSTextField.labelWithString_(text)
        field.setFrame_(NSMakeRect(LABEL_X, y, W - 90, 32))
        field.setFont_(NSFont.systemFontOfSize_(11))
        field.setTextColor_(NSColor.secondaryLabelColor())
        view.addSubview_(field)
        return field

    def make_switch(self, view, key: str, y: int):
        btn = NSButton.checkboxWithTitle_target_action_("", self, "toggle:")
        btn.setFrame_(NSMakeRect(CONTROL_X, y, 28, 22))
        btn.setIdentifier_(key)
        view.addSubview_(btn)
        self.controls[key] = btn
        return btn

    def make_popup(self, view, key: str, choices: list[tuple[str, object]], y: int):
        pop = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(CONTROL_X, y, CONTROL_W, 26), False)
        pop.addItemsWithTitles_([label for label, _ in choices])
        pop.setIdentifier_(key)
        pop.setTarget_(self)
        pop.setAction_("choose:")
        for i, (_, value) in enumerate(choices):
            pop.itemAtIndex_(i).setRepresentedObject_(value)
        view.addSubview_(pop)
        self.controls[key] = pop
        return pop

    def make_button(self, view, title: str, action: str, y: int, x: int = CONTROL_X, w: int = 150):
        btn = NSButton.buttonWithTitle_target_action_(title, self, action)
        btn.setFrame_(NSMakeRect(x, y, w, 26))
        btn.setBezelStyle_(1)
        view.addSubview_(btn)
        return btn

    # -- tabs -----------------------------------------------------------
    def fill_tab(self, title: str, view) -> None:
        y = 330
        if title == "General":
            self.make_label(view, "Hotkey", y)
            self.make_popup(view, "HOTKEY", [("Right Command", "right_command"),
                                        ("Right Option", "right_option")], y)
            y -= ROW_H
            self.make_label(view, "Mode", y)
            self.make_popup(view, "DICTATION_MODE", [("Hold to talk", "push"),
                                                ("Tap to start and stop", "toggle")], y)
            y -= ROW_H
            self.make_label(view, "Language", y)
            self.make_popup(view, "LANGUAGE", [("English", "en"), ("Detect automatically", "")], y)
            y -= ROW_H + 6
            self.make_label(view, "Show the pill", y)
            self.make_switch(view, "OVERLAY", y)
            y -= ROW_H
            self.make_label(view, "Liquid Glass pill", y)
            self.make_switch(view, "GLASS", y)
            y -= ROW_H
            self.make_label(view, "Paste into the focused app", y)
            self.make_switch(view, "PASTE", y)
            y -= ROW_H
            self.make_label(view, "Add a trailing space", y)
            self.make_switch(view, "TRAILING_SPACE", y)
            y -= ROW_H
            self.make_label(view, "Start at login", y)
            self.make_switch(view, "START_AT_LOGIN", y)
            self.make_note(view, "Swallowing the hotkey is what stops it reaching the "
                             "app you are dictating into.", 40)

        elif title == "Audio":
            self.make_label(view, "Microphone", y)
            self.make_popup(view, "MIC_DEVICE", [("System default", None)], y)
            y -= ROW_H
            self.make_label(view, "Keep the engine warm", y)
            self.make_popup(view, "KEEP_WARM_SEC", [("Every 5 minutes", 300),
                                               ("Every 10 minutes", 600),
                                               ("Off", 0)], y)
            y -= ROW_H
            self.make_label(view, "Silence gate", y)
            self.make_popup(view, "MIN_PEAK", [("Learned (recommended)", 0.025),
                                          ("Stricter 0.04", 0.04),
                                          ("Looser 0.012", 0.012)], y)
            y -= ROW_H + 6
            self.make_button(view, "Check permissions", "checkPermissions:", y, w=170)
            y -= ROW_H
            self._audio_status = self.make_note(view, "", y)

        elif title == "Transcription":
            self.make_label(view, "Model", y)
            self.make_popup(view, "MODEL_FILE", [("large-v3-turbo", "ggml-large-v3-turbo.bin")], y)
            y -= ROW_H
            self.make_label(view, "Encoder window", y)
            self.make_popup(view, "AUDIO_CTX", [("12.8 s (fast)", 640),
                                           ("15.4 s", 768),
                                           ("10.2 s (fastest, shorter takes)", 512),
                                           ("30 s (slowest, most accurate)", 1500)], y)
            y -= ROW_H + 6
            self.make_label(view, "Vocabulary", y, bold=True)
            y -= 22
            scroll = NSScrollView.alloc().initWithFrame_(
                NSMakeRect(LABEL_X, 92, W - 76, y - 92))
            text = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, W - 76, y - 92))
            text.setFont_(NSFont.userFixedPitchFontOfSize_(12))
            text.setRichText_(False)
            scroll.setDocumentView_(text)
            scroll.setHasVerticalScroller_(True)
            scroll.setBorderType_(2)
            view.addSubview_(scroll)
            self._vocab = text
            self.make_note(view, "One term per line. The first three carry the most "
                             "weight; near-misses are corrected automatically.", 52)
            self.make_button(view, "Save vocabulary", "saveVocabulary:", 20, w=170)

        else:  # Advanced
            self.make_button(view, "Open config file", "openConfig:", y, w=170)
            y -= ROW_H
            self.make_button(view, "Open vocabulary", "openVocabulary:", y, w=170)
            y -= ROW_H
            self.make_button(view, "Open log", "openLog:", y, w=170)
            y -= ROW_H + 6
            self._advanced_status = self.make_note(
                view, "Nemo · engine and model appear here", 196)
            self.make_note(view, "Everything these buttons open is plain text. "
                                 "The window above is the normal way to change things.",
                           140)

    # -- state ----------------------------------------------------------
    def refresh_values(self) -> None:
        import nemo
        values = {
            "HOTKEY": nemo.HOTKEY,
            "DICTATION_MODE": nemo.DICTATION_MODE,
            "LANGUAGE": nemo.LANGUAGE,
            "OVERLAY": bool(nemo.OVERLAY),
            "GLASS": bool(nemo.GLASS),
            "PASTE": bool(nemo.PASTE),
            "TRAILING_SPACE": bool(nemo.TRAILING_SPACE),
            "KEEP_WARM_SEC": int(nemo.KEEP_WARM_SEC),
            "MIN_PEAK": 0.025 if nemo.MIN_PEAK >= 0.025 else nemo.MIN_PEAK,
            "MODEL_FILE": nemo.MODEL_FILE,
            "AUDIO_CTX": int(nemo.AUDIO_CTX),
            "START_AT_LOGIN": bool(nemo.startup_get()),
        }
        for key, value in values.items():
            ctrl = self.controls.get(key)
            if ctrl is None:
                continue
            if key == "START_AT_LOGIN":
                ctrl.setState_(1 if value else 0)
            elif isinstance(ctrl, NSButton):
                ctrl.setState_(1 if value else 0)
            else:
                for i in range(ctrl.numberOfItems()):
                    if ctrl.itemAtIndex_(i).representedObject() == value:
                        ctrl.selectItemAtIndex_(i)
                        break

        # microphones, freshened every time the window is shown
        pop = self.controls.get("MIC_DEVICE")
        if pop is not None:
            pop.removeAllItems()
            for label, value in nemo.mic_choices():
                pop.addItemWithTitle_(label)
                pop.itemAtIndex_(pop.numberOfItems() - 1).setRepresentedObject_(value)
            current = nemo.MIC_DEVICE
            for i in range(pop.numberOfItems()):
                if pop.itemAtIndex_(i).representedObject() == current:
                    pop.selectItemAtIndex_(i)
                    break

        model_pop = self.controls.get("MODEL_FILE")
        if model_pop is not None:
            model_pop.removeAllItems()
            for name, entry in nemo.MODEL_CATALOG.items():
                model_pop.addItemWithTitle_(f"{name}  ({entry[1] / 1e9:.1f} GB)")
                model_pop.itemAtIndex_(model_pop.numberOfItems() - 1) \
                    .setRepresentedObject_(entry[0])
            for i in range(model_pop.numberOfItems()):
                if model_pop.itemAtIndex_(i).representedObject() == nemo.MODEL_FILE:
                    model_pop.selectItemAtIndex_(i)
                    break

        if self._vocab is not None:
            try:
                self._vocab.setString_(nemo.VOCAB_FILE.read_text(encoding="utf-8")
                                       if nemo.VOCAB_FILE.exists() else "")
            except Exception:
                pass

        gate = nemo.effective_min_peak()
        takes = len(nemo._load_peaks())
        engine = "backend unknown"
        try:
            if self.app is not None and getattr(self.app, "server", None):
                engine = nemo.engine_phrase(self.app.server.backend())
        except Exception:
            pass
        if self._audio_status is not None:
            self._audio_status.setStringValue_(
                f"Gate {gate:.4f}, learned from {takes} takes.")
        if self._advanced_status is not None:
            size = ""
            try:
                size = f" · {nemo.MODEL.stat().st_size / 1e9:.1f} GB"
            except Exception:
                pass
            self._advanced_status.setStringValue_(
                f"Nemo {nemo.APP_VERSION}  ·  {engine}\n{nemo.MODEL.name}{size}")

    # -- actions --------------------------------------------------------
    def toggle_(self, sender) -> None:
        key = sender.identifier()
        if key == "START_AT_LOGIN":
            self.set_startup(bool(sender.state()))
            return
        self.apply_key(key, bool(sender.state()))

    def choose_(self, sender) -> None:
        key = sender.identifier()
        value = sender.selectedItem().representedObject()
        self.apply_key(key, value)

    def set_startup(self, on: bool) -> None:
        import nemo
        ok, message = nemo.startup_set(on)
        self.log(f"start at login -> {message}")
        if not ok:
            self.notify_user("Start at login failed")

    def apply_key(self, key: str, value) -> None:
        import nemo
        if not nemo.set_setting(key, value):
            return
        self.log(f"settings: {key} = {value!r}")
        try:
            self.on_apply(key)
        except Exception as exc:
            self.log(f"applying {key} failed: {exc}")
        self.refresh_values()

    def notify_user(self, text: str) -> None:
        if self.app is not None and hasattr(self.app, "say"):
            try:
                self.app.say(text)
            except Exception:
                pass

    def saveVocabulary_(self, sender) -> None:
        import nemo
        try:
            nemo.VOCAB_FILE.parent.mkdir(parents=True, exist_ok=True)
            nemo.VOCAB_FILE.write_text(self._vocab.string(), encoding="utf-8")
            nemo.vocabulary_prompt()      # refreshes the mtime cache
            self.log("vocabulary saved")
            self.notify_user("Vocabulary saved")
        except Exception as exc:
            self.log(f"could not save vocabulary: {exc}")
            self.notify_user("Vocabulary not saved")

    def checkPermissions_(self, sender) -> None:
        from nemo_platform.macos.dialog import explain_permissions
        from nemo_platform.macos.permissions import (missing, open_settings,
                                                     running_identity)
        which = explain_permissions(missing(), running_identity())
        if which:
            open_settings(which)

    def openConfig_(self, sender) -> None:
        import nemo
        self.open_path(nemo._CONFIG_FILE)

    def openVocabulary_(self, sender) -> None:
        import nemo
        self.open_path(nemo.VOCAB_FILE)

    def openLog_(self, sender) -> None:
        import nemo
        self.open_path(nemo.LOGFILE)

    def open_path(self, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text("", encoding="utf-8")
            subprocess.run(["open", "-t", str(path)], check=False)
        except Exception as exc:
            self.log(f"could not open {path}: {exc}")

    # -- window delegate ------------------------------------------------
    def windowWillClose_(self, note) -> None:
        try:
            NSApplication.sharedApplication().setActivationPolicy_(
                NSApplicationActivationPolicyAccessory)
        except Exception:
            pass
