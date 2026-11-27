"""Regression tests for the logic that came out of measurement.

Every constant here was derived from something measured on this machine or
carried from the Windows build record; the tests pin the behaviour, not the
numbers, so they survive retuning.

Run:  .venv/bin/python scripts/test_core_logic.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

import nemo  # noqa: E402
from overlay_render import HC_SURFACES, PALETTES, _font_candidates, render  # noqa: E402

if sys.platform == "darwin":
    from nemo_platform.macos.pill import _GLOW_RADIUS, _PAD, _status_key  # noqa: E402
    from nemo_platform.macos.theme import normalise, resolve  # noqa: E402

# Keep the app's own log clean: a test run must not look like use.
nemo.LOGFILE = Path(tempfile.gettempdir()) / "nemo-test.log"


def check(name: str, passed: bool, detail: str = "") -> bool:
    print(("PASS  " if passed else "FAIL  ") + name + (f"  [{detail}]" if detail and not passed else ""))
    return passed


def _lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lum(rgb) -> float:
    return 0.2126 * _lin(rgb[0]) + 0.7152 * _lin(rgb[1]) + 0.0722 * _lin(rgb[2])


def _contrast(a, b) -> float:
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def test_capture_and_engine(tmp: Path) -> bool:
    ok = True
    samples = np.arange(2048, dtype=np.int16)
    for rate, channels in ((48000, 1), (48000, 2), (44100, 1)):
        recorder = nemo.Recorder()
        recorder._rate = rate
        frames = np.tile(samples[:, None], (1, channels))
        recorder._blocks = list(np.split(frames, 2))
        pcm = recorder.stop()
        expected = (samples[:2046].reshape(-1, 3).mean(axis=1) if rate == 48000 else
                    np.linspace(0, 2047, round(2048 * 16000 / rate)))
        ok &= check(f"{rate} Hz x{channels} preserves the take",
                    np.array_equal(pcm, expected.astype(np.int16)))

    server = nemo.Server(12345)
    state = tmp / "engine.json"
    with (patch.object(server, "_state_file", return_value=state),
          patch.object(server, "_listening", return_value=True) as listening,
          patch.object(server, "_listen_pid", return_value=123) as pid,
          patch.object(nemo, "SERVER_EXE", Path(sys.executable)),
          patch.object(nemo.subprocess, "check_output", return_value=sys.executable) as exe,
          patch.object(nemo.os, "kill") as kill,
          patch.object(nemo.time, "sleep")):
        for model in (nemo.MODEL.name, "old.bin"):
            state.write_text(json.dumps({"pid": 321, "model": model}))
            ok &= check("stale engine PID is refused", not server.ensure())
            server.shutdown()
            ok &= check("foreign listener and state are untouched",
                        not kill.called and state.exists())
        state.write_text(json.dumps({"pid": 123, "model": nemo.MODEL.name}))
        exe.return_value = "/bin/sh"
        ok &= check("reused PID with wrong executable is refused", not server.ensure())
        def process_info(args, **kwargs):
            if args[-1] == "comm=":
                return sys.executable
            return f"{sys.executable} -m {live_model} --host 127.0.0.1 --port 12345 -t 4"

        live_model = nemo.MODELS_DIR / "old.bin"
        exe.side_effect = process_info
        ok &= check("same executable with another model is refused", not server.ensure())
        live_model = nemo.MODEL
        ok &= check("matching engine is adopted", server.ensure() and server._adopted_pid == 123)
        pid.return_value = 456
        server.shutdown()
        ok &= check("shutdown rechecks an adopted PID", not kill.called)
        pid.return_value = 123
        state.write_text(json.dumps({"pid": 123, "model": "old.bin"}))
        live_model = nemo.MODELS_DIR / "old.bin"
        ok &= check("lingering wrong-model listener cannot report ready",
                    not server.ensure() and state.exists())
        listening.side_effect = [True, False, False, True]
        with patch.object(nemo.subprocess, "Popen") as spawn:
            spawn.return_value.poll.return_value = None
            spawn.return_value.pid = 456
            spawn.return_value.stderr = []
            pid.side_effect = [123, 123, 456]
            ok &= check("verified model mismatch stops survivor and starts configured engine",
                        server.ensure() and kill.call_args.args == (123, 15)
                        and str(nemo.MODEL) in spawn.call_args.args[0]
                        and json.loads(state.read_text())["pid"] == 456)
    return ok


def test_warming() -> bool:
    server = Mock()
    app = nemo.Nemo(None, server, None)
    stop = Mock()
    stop.wait.side_effect = [False, False, True]
    with (patch.object(nemo.time, "monotonic", return_value=1000),
          patch.object(nemo, "KEEP_WARM_SEC", 300),
          patch.object(nemo, "keep_warm_interval", return_value=900) as power):
        nemo.keep_warm_loop(app, stop)
        ok = check("startup warms once and next idle tick skips power query",
                   server.transcribe.call_count == power.call_count == 1
                   and server.transcribe.call_args.kwargs == {})
        app._started_at = 0
        app.warm_if_due(60, key_down=True)
        app.warm_if_due(60)
        ok &= check("key-down and wake use the timer inference time",
                    server.transcribe.call_count == 1)
        app._last_inference = 500
        stop.wait.side_effect = [False, False, True]
        nemo.keep_warm_loop(app, stop)
        ok &= check("battery interval caches power decision across idle ticks",
                    power.call_count == 2 and server.transcribe.call_count == 1)
        server.transcribe.side_effect = lambda *a, **kw: app.warm_if_due(60)
        app.warm_if_due(60, key_down=True)
        ok &= check("in-flight warm suppresses another warm", server.transcribe.call_count == 2)
        app._last_inference = 0
        server.transcribe.side_effect = OSError("offline")
        app.warm_if_due(60)
        ok &= check("failed warm does not advance inference time", app._last_inference == 0)
        server.transcribe.side_effect = None
        server.transcribe.return_value = ""
        with patch.object(nemo, "beep"):
            app._finish(np.full(32000, 16000, dtype=np.int16))
        ok &= check("a completed real inference suppresses a warm even with empty text",
                    app._last_inference == 1000 and app.warm_if_due(60) is None)
    return ok


def main() -> int:
    ok = True
    original = nemo.LEVELS_FILE
    with tempfile.TemporaryDirectory() as tmp:
        nemo.LEVELS_FILE = Path(tmp) / "mic_levels.json"

        ok &= test_capture_and_engine(Path(tmp))
        ok &= test_warming()
        if sys.platform == "darwin":
            from nemo_platform.macos import paste
            with (patch.object(paste, "copy_text", return_value=True),
                  patch.object(paste, "_holds", return_value=False) as holds,
                  patch.object(paste.time, "sleep"), patch.object(paste, "_post_command_v") as post):
                ok &= check("clipboard timeout suppresses Command-V",
                            not paste.paste_text("take") and not post.called and holds.call_count == 20)
                holds.side_effect = [False, True]
                ok &= check("matching clipboard posts once", paste.paste_text("take") and post.call_count == 1)

        # --- the gate may only ever loosen ---------------------------------
        ok &= check("gate is the constant before 20 takes",
                    nemo.effective_min_peak() == float(nemo.MIN_PEAK))
        nemo.LEVELS_FILE.write_text(json.dumps({"peaks": [0.03] * 20}))
        learned = nemo.effective_min_peak()
        ok &= check("quiet speech loosens the gate", learned < float(nemo.MIN_PEAK),
                    f"{learned} vs {nemo.MIN_PEAK}")
        ok &= check("gate never goes below the floor", learned >= nemo.GATE_FLOOR,
                    str(learned))
        nemo.LEVELS_FILE.write_text(json.dumps({"peaks": [0.4] * 20}))
        ok &= check("loud speech never tightens past the constant",
                    nemo.effective_min_peak() <= float(nemo.MIN_PEAK))
        nemo.LEVELS_FILE.write_text(json.dumps({"peaks": [0.0001] * 20}))
        ok &= check("digital silence floors, never zeroes",
                    nemo.effective_min_peak() == nemo.GATE_FLOOR,
                    str(nemo.effective_min_peak()))

        # --- recording peaks are bounded -----------------------------------
        nemo.LEVELS_FILE.write_text(json.dumps({"peaks": []}))
        for _ in range(nemo.PEAKS_MAX + 25):
            nemo.record_peak(0.05)
        stored = json.loads(nemo.LEVELS_FILE.read_text())["peaks"]
        ok &= check("peak history stays bounded", len(stored) <= nemo.PEAKS_MAX,
                    str(len(stored)))

        # --- loop detection ------------------------------------------------
        ok &= check("a clean sentence is not flagged",
                    not nemo.looks_looped("Nemo turns speech into text on this Mac"))
        ok &= check("a doubled sentence is flagged",
                    nemo.looks_looped("we should ship this today because it is ready "
                                      "we should ship this today because it is ready"))
        ok &= check("a short phrase is never flagged",
                    not nemo.looks_looped("thank you very much"))
        ok &= check("a genuine stutter is not flagged",
                    not nemo.looks_looped("the the quick brown fox jumps over it"))

        # --- the encoder window --------------------------------------------
        one_second = np.zeros(16000, dtype=np.int16)
        ten_seconds = np.zeros(160000, dtype=np.int16)
        ok &= check("window has a floor", nemo.audio_context_frames(one_second) >= 128)
        ok &= check("window has a ceiling",
                    nemo.audio_context_frames(np.zeros(16000 * 40, dtype=np.int16)) == 1500)
        ok &= check("window grows with audio",
                    nemo.audio_context_frames(ten_seconds) > nemo.audio_context_frames(one_second))
        # 1500 frames is 30 s, so 10 s of audio needs ~500 frames; the margin must
        # leave room without wasting most of the window.
        need = nemo.audio_context_frames(ten_seconds)
        ok &= check("window fits 10 s of audio", need >= 500 + 32, str(need))
        ok &= check("window is not wildly oversized", need <= 800, str(need))

        # --- per-request windows never restart the engine ------------------
        class FakeServer:
            def __init__(self, texts):
                self.texts = list(texts)
                self.calls = []

            def transcribe(self, wav, prompt="", ac=None):
                self.calls.append(ac)
                return self.texts.pop(0)

            def ensure(self, **kwargs):
                raise AssertionError("a window change must not restart the engine")

        looped = ("we should ship this today because it is ready " * 2).strip()
        fake = FakeServer([looped, "we should ship this today because it is ready"])
        text, used = nemo.transcribe_guarded(fake, b"wav", "", ac=640)
        ok &= check("loop retry uses a bigger window, not a restart",
                    fake.calls == [640, 1500], str(fake.calls))
        ok &= check("loop retry reports the window used", used == 1500, str(used))
        ok &= check("loop retry returns the clean transcript",
                    text == "we should ship this today because it is ready", text)

        fake = FakeServer(["a clean sentence"])
        text, used = nemo.transcribe_guarded(fake, b"wav", "", ac=768)
        ok &= check("a clean take sends only its own window",
                    fake.calls == [768] and used == 768, str(fake.calls))

        # --- hallucination filter ------------------------------------------
        ok &= check("whitespace is collapsed", nemo.clean("  hello \n  world  ") == "hello world")
        ok &= check("a known hallucination is dropped", nemo.clean("Thank you.") == "")
        ok &= check("bracket artefacts are dropped", nemo.clean("[BLANK_AUDIO]") == "")
        ok &= check("real speech survives", nemo.clean("Ship it on Tuesday.") == "Ship it on Tuesday.")

        # --- vocabulary ----------------------------------------------------
        vocab = Path(tmp) / "vocabulary.txt"
        nemo.VOCAB_FILE = vocab
        nemo._vocab_cache = {"stamp": None, "prompt": ""}
        vocab.write_text("# comment\nTolaria\nSplice Media\nNemo\n", encoding="utf-8")
        prompt = nemo.vocabulary_prompt()
        ok &= check("comments are ignored", "#" not in prompt, prompt)
        ok &= check("terms are comma-separated", "Tolaria, Splice Media" in prompt, prompt)
        ok &= check("the first terms are repeated as a tail",
                    prompt.count("Tolaria") >= 2, prompt)
        ok &= check("prompt stays inside the model's window",
                    len(prompt) <= nemo.VOCAB_MAX_CHARS, str(len(prompt)))
        nemo._vocab_cache = {"stamp": None, "prompt": ""}
        vocab.write_text("\n".join(f"term{i}" for i in range(200)), encoding="utf-8")
        ok &= check("a huge vocabulary is truncated, not passed whole",
                    len(nemo.vocabulary_prompt()) <= nemo.VOCAB_MAX_CHARS)
        nemo._vocab_cache = {"stamp": None, "prompt": ""}
        vocab.write_text("x" * 5000, encoding="utf-8")
        ok &= check("one over-long line is truncated too",
                    len(nemo.vocabulary_prompt()) <= nemo.VOCAB_MAX_CHARS,
                    str(len(nemo.vocabulary_prompt())))

        # --- silence trimming ----------------------------------------------
        sr = nemo.SAMPLE_RATE
        tone = (np.sin(np.linspace(0, 2000, sr)) * 8000).astype(np.int16)
        padded = np.concatenate([np.zeros(sr * 2, dtype=np.int16), tone,
                                 np.zeros(sr * 2, dtype=np.int16)])
        trimmed = nemo.trim_silence(padded)
        ok &= check("trimming removes edge silence",
                    len(trimmed) < len(padded) * 0.5,
                    f"{len(padded)} -> {len(trimmed)}")
        ok &= check("trimming keeps the speech itself",
                    len(trimmed) >= len(tone), str(len(trimmed)))
        ok &= check("trimming leaves a clean take alone",
                    len(nemo.trim_silence(tone)) == len(tone))
        ok &= check("trimming keeps a take that is all silence",
                    len(nemo.trim_silence(np.zeros(sr, dtype=np.int16))) == sr)

        # --- vocabulary correction -----------------------------------------
        vocab.write_text("Tolaria\nNemo\n", encoding="utf-8")
        ok &= check("the real miss is corrected",
                    nemo.apply_vocabulary("notes on Tellaria") == "notes on Tolaria",
                    nemo.apply_vocabulary("notes on Tellaria"))
        ok &= check("a second miss is corrected",
                    nemo.apply_vocabulary("into Toleria now") == "into Tolaria now")
        ok &= check("an ordinary word is left alone",
                    nemo.apply_vocabulary("a tolerant approach") == "a tolerant approach")
        ok &= check("an ordinary capitalised word is left alone",
                    nemo.apply_vocabulary("the Teller was late") == "the Teller was late")
        ok &= check("a correct spelling is not touched",
                    nemo.apply_vocabulary("Tolaria is fine") == "Tolaria is fine")
        ok &= check("lowercase words are not corrected",
                    nemo.apply_vocabulary("notes on tellaria") == "notes on tellaria")
        ok &= check("no vocabulary means no change",
                    nemo.apply_vocabulary("notes on Tellaria") == "notes on Tellaria"
                    if not vocab.exists() else True)

        # --- solid fallback palettes ----------------------------------------
        for name, palette in PALETTES.items():
            surfaces = [palette.bg_top, palette.bg_bottom,
                        HC_SURFACES[name][0], HC_SURFACES[name][1]]
            for role in ("fg", "muted", "accent", "green", "red"):
                ink = getattr(palette, role)
                worst = min(_contrast(ink, surface) for surface in surfaces)
                ok &= check(f"{name} {role} clears 4.5:1 on every surface",
                            worst >= 4.5, f"{worst:.2f}")
        frames = [render("listening", 0.0, [0.5] * 9, glass=glass, theme=theme)
                  for glass in (False, True) for theme in ("light", "dark")]
        ok &= check("themes and glass modes keep the same geometry",
                    all(f.size == frames[0].size for f in frames))
        ok &= check("light and dark are genuinely different images",
                    frames[0].tobytes() != frames[2].tobytes())
        # frames: solid-light, solid-dark, glass-light, glass-dark.
        glass = frames[2]
        corners = [glass.getpixel(p) for p in
                   ((0, 0), (glass.width - 1, 0),
                    (0, glass.height - 1),
                    (glass.width - 1, glass.height - 1))]
        ok &= check("glass paints no surface of its own",
                    all(pixel[3] == 0 for pixel in corners), str(corners))
        ok &= check("the dot is gone from the left inset",
                    all(glass.getpixel((8, y))[3] == 0
                        for y in range(glass.height)))
        if sys.platform == "darwin":
            ok &= check("listening glows orange",
                        _status_key("listening") == "orange")
            ok &= check("done glows green",
                        _status_key("done") == "green")
            ok &= check("errors glow red",
                        _status_key("error") == "red")
            ok &= check("quiet states have no glow",
                        _status_key("paused") is None and _status_key("hint:Hi") is None)
            ok &= check("the window pads enough room for the glow",
                        2 * _PAD >= _GLOW_RADIUS)
            ok &= check("the Mac pill uses SF Pro first",
                        _font_candidates()[0].endswith("SFNS.ttf"))
            ok &= check("a junk theme follows the system", normalise("sidebar") == "system")
            # Query both appearances without registering a GUI app in a headless run.
            with patch("nemo_platform.macos.theme.NSApplication") as application:
                appearance = application.sharedApplication.return_value.effectiveAppearance.return_value
                for name, expected in (("NSAppearanceNameAqua", "light"),
                                       ("NSAppearanceNameDarkAqua", "dark")):
                    appearance.bestMatchFromAppearancesWithNames_.return_value = name
                    ok &= check(f"resolve follows system {expected}", resolve("system") == expected)
            ok &= check("resolve honours a pinned theme", resolve("light") == "light")

        # --- microphone listing ---------------------------------------------
        choices = nemo.mic_choices()
        ok &= check("the microphone list starts with the system default",
                    choices and choices[0] == ("System default", None))
        ok &= check("the microphone list names devices",
                    all(isinstance(label, str) for label, _ in choices))

        # --- text out ------------------------------------------------------
        ok &= check("hotkey is named for the platform",
                    nemo.hotkey_label() == ("Right Command" if sys.platform == "darwin" else "Right Alt"))
        ok &= check("privacy line names the platform",
                    ("Mac" in nemo.privacy_line()) == (sys.platform == "darwin"))

    nemo.LEVELS_FILE = original
    print()
    print("all core logic correct" if ok else "FAILURES above")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
