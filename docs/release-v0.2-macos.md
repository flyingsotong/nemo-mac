# Nemo for Mac 0.2

Offline dictation for macOS: hold **Right Command**, speak, let go. Whisper runs on
Metal via a resident whisper-server, the text lands where your cursor is, and audio
never leaves the machine.

This is the macOS build. The Windows build is unchanged on `main`; the two share one
core and differ only in the host layer, which lives in `nemo_platform/macos/`.

## Install

```sh
brew install whisper.cpp          # the Metal engine; not bundled
git clone https://github.com/flyingsotong/nemo && cd nemo
git checkout macos
./build.sh                        # builds and signs dist/Nemo.app
open dist/Nemo.app
```

The model (1.6 GB, `large-v3-turbo`) is fetched and SHA-256 verified on first run.

You will be asked for **Microphone** and **Accessibility**. Accessibility is granted
per code identity: if you rebuild with a different signing identity, expect to grant
it again. `IDENTITY="Developer ID Application: …" ./build.sh` avoids that.

## What it does

- Push-to-talk on Right Command, swallowed so it never reaches the focused app.
- A Liquid Glass pill at the bottom of the screen with a live level meter, and a menu
  bar icon that turns **orange** while the mic is open.
- Menu bar: engine and model as the running process reports them, pause, the last
  transcript, settings and vocabulary, reload, start at login, check permissions.
- Vocabulary as Whisper's initial prompt, re-read per utterance.
- Keep-warm inference while idle, a learned silence gate, and honest failure
  messages — "No speech" is distinguished from "No mic audio".

## Measured on an M5 (14-inch MacBook Pro, 16 GB)

| What | Value |
|---|---|
| Release to text, 6 s take | **301 ms** |
| Engine round trip, 640-frame window | ~290 ms |
| Pill frame, 2x Retina | 1.91 ms with Liquid Glass (1.99 ms painted) |
| Cold start to usable | 1.10 s |
| Idle, hidden | 0.2% of one core (app), 0.4% (engine) |
| `small.en` instead of turbo | 182 ms, at the cost of coined names |

## Known behaviour, not bugs

- **Whisper's window is the latency.** It always encodes a fixed window, so a 2 s
  take costs nearly what a 12 s one does. `AUDIO_CTX` trades quality for speed;
  below 640 frames this build was observed repeating a sentence, which is why it
  detects that and retries at the full window.
- **The vocabulary prompt is positional.** Terms more than about three tokens from
  the end of the prompt have no effect. The first three are repeated as a tail.
- **Password fields cannot be dictated into.** macOS blocks every event tap under
  secure input; that is correct behaviour.
- **`audio_ctx` must not vary per request.** This build corrupts the next decode if
  it does, so the window is a server setting and a long take restarts the engine.
- The pill says `Copied` only when the text actually reached the clipboard. If the
  paste path fails, it says an error instead of a comfortable lie.

## Not in this version

Spoken formatting, a microphone picker, engine swaps (Core ML, MLX), any cloud path,
history on disk. The same list as Windows, in the same order.

MIT licensed; see `LICENSE` and `THIRD-PARTY-NOTICES.md`. The Mac build has no LGPL
dependencies: the hotkey is a `CGEventTap` and the menu bar item is an
`NSStatusItem`, not `pynput` and `pystray`.
