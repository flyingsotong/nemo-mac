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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

import nemo  # noqa: E402


def check(name: str, passed: bool, detail: str = "") -> bool:
    print(("PASS  " if passed else "FAIL  ") + name + (f"  [{detail}]" if detail and not passed else ""))
    return passed


def main() -> int:
    ok = True
    original = nemo.LEVELS_FILE
    with tempfile.TemporaryDirectory() as tmp:
        nemo.LEVELS_FILE = Path(tmp) / "mic_levels.json"

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
