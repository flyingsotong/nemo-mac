# macOS measurement log (2026-11-04)

Working notes kept from the bring-up. **`MACOS.md` is the user-facing record; this
file is the trail of what was tested and what was wrong.** Several early
conclusions here were later corrected — those corrections are written inline, so
nobody re-derives them.

## Machine

MacBook Pro `Mac17,2`, M5, 4 performance cores, 16 GB, macOS 26.x/27.3 build
26C5035r. `THREADS=4`. Python 3.15 with pyobjc 13 and PyInstaller 6.22.3
(`cp315` wheels exist, so no downgrade).

## Engine

- `brew install whisper.cpp` → 1.9.5. **Metal is in the bottle**; the §7.2 source
  build is unnecessary. A native source build was tried anyway and was *slower*
  (650 ms vs 490 ms encode), so the bottle stays.
- Model `ggml-large-v3-turbo.bin`, 1,624,555,275 bytes, SHA-256 verified.
- Banner to parse: `ggml_metal_init: found device: Apple M5`,
  `whisper_backend_init_gpu: using MTL0 backend`.
- Flags that differ from the spec: `-ac/--audio-ctx` (not `--audio-context`),
  flash attention is **on by default** (`-nfa` disables), `-bs 1 -bo 1` is greedy.

## The four findings that changed the design

1. **`audio_ctx` is accepted per request — and must not be used that way.**
   It is honoured (129/181/448 ms at 256/512/1500), which made per-utterance
   windows look ideal. But varying it across requests **corrupts the next
   decode**, deterministically: after a 1500-frame request, a 340-frame request
   returned `"and it Aujourd sip."` five times in a row. A *fixed* window is
   stable. So the window is a server flag, and a long take costs one restart.
2. **A small window can make the decoder loop.** Fixed windows, same two clips:
   640 loops the short one, 768 loops the long one, 900 and 1500 are clean on
   both in this sample. (The earlier "768 duplicated, 900 mangled" result was
   taken while switching `audio_ctx` per request, so it belongs to finding 1.)
   No small window was reliably clean, so the app keeps 640 on the fast path,
   detects an eight-word repeat, and retries at 1500 for the rest of the session.
3. **The encoder is the latency, and it scales with model width, not count.**
   large-v3-turbo keeps Whisper's 32-layer encoder: 490 ms encode, 120 ms decode.
   `small.en`: 100 ms encode. CPU-only encode of turbo: 8.1 s, so Metal really is
   doing the work.
4. **The vocabulary prompt is positional.** A term four tokens from the end of the
   prompt does nothing; the last two or three decide the spelling. A single term
   (`Tolaria`) failed; the same term with a longer tail, or repeated at the end,
   worked. Hence the emphasis tail of the first three terms in
   `vocabulary_prompt()`. This is a weaker feature than Windows had.

Also: `-mc 0` is needed, or one dictation's text leaks into the next.

## Latency, HTTP round trip, warm server

| Window | 4.7 s clip |
|---|---|
| 1500 | 448 ms |
| 640 | 284 ms |
| 512 | 181 ms |
| 256 | 129 ms |

## Verified

- Tap: `CGEventTapCreate` succeeds with Accessibility already granted to the
  running Python. Synthetic `flagsChanged` with key code 61 dispatches press and
  release, and is swallowed. (No human keypress needed for this test.)
- Full loop driven synthetically: press → record → gate → log
  (`too quiet (peak 0.0142, gate 0.0250)`), pill shows Listening with bars.
- Pill rendering: all eight states captured from the real window; text crisp at
  2x backing scale; sits above the Dock, over other windows.
- Menu bar item installs and shows a template waveform.
- Mic opens and meters; **ambient alone peaks at 0.0139**, above the old 0.012
  gate, so `MIN_PEAK` starts at 0.025 here.
- Bundle: 50 MB, signed with a stable Apple Development identity, `LSUIElement`,
  `NSMicrophoneUsageDescription` present.

## Not verified (needs a human)

- Real speech end to end through the real hotkey, into a document the user chose
  (paste was proven with Command-V into a TextEdit document, but not with Nemo
  driving a focused foreign app at the same time).
- Pause, menu actions, start at login, wake handling.
- The bundle's Accessibility grant (the source run's grant does not carry over —
  TCC is per code identity).

## Harness limits worth remembering

- A bare Python process cannot bring its own window to the front, so a window I
  create is never the real focus target. Paste must be tested against an app that
  `open -a` can activate (TextEdit worked).
- TCC dialogs ignore synthetic key events, so they cannot be dismissed from a
  script. Do not drive other apps with AppleScript here: it raises an Automation
  prompt that has to be clicked by hand.

## Open, deliberately

- Bundling the engine properly (`install_name_tool` over libwhisper + ggml) so the
  .app does not depend on Homebrew.
- Whether CoreML/ANE would encode faster than 490 ms.
- A deterministic spelling fix for vocabulary, since the prompt alone is weak.
