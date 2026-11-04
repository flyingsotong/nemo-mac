# Nemo on macOS

Hold **Right Option**, speak, release. The text appears where the cursor is.
Offline: audio goes to a whisper server on `127.0.0.1:8129` and nowhere else.

This is the macOS build of [Nemo](README.md). The Windows build is the reference;
this one reproduces the behaviour contract in `macos-build-spec.md` and diverges
only where the Mac or the engine forced it, which is recorded at the bottom.

## Install (this machine)

```sh
brew install whisper.cpp          # Metal-enabled bottle; no overlay needed
./build.sh                        # builds and signs dist/Nemo.app
open dist/Nemo.app
```

The model is `~/Library/Application Support/Nemo/models/ggml-large-v3-turbo.bin`,
downloaded and SHA-256 verified against the catalogue on first run (or with
`--fetch-model`).

## Files

Everything the app owns lives in `~/Library/Application Support/Nemo/`:

| File | What it is |
|---|---|
| `config.json` | overrides any of the settings below |
| `vocabulary.txt` | one term per line; biases spelling |
| `models/` | the ggml model |
| `mic_levels.json` | the learned silence gate |
| `nemo.log` | plain text, trimmed to 512 KB / last 400 lines |

The `.app` is only the conductor. The engine binary is Homebrew's.

## Settings

`config.json`, read at start and on **Reload settings**:

| Key | Default | Meaning |
|---|---|---|
| `SUPPRESS_HOTKEY` | `true` | swallow Right Option; `false` lets it through |
| `DICTATION_MODE` | `"push"` | `"toggle"` for tap to start, tap to stop |
| `LANGUAGE` | `"en"` | `""` to auto-detect |
| `MODEL_FILE` | `ggml-large-v3-turbo.bin` | which file in `models/` |
| `MIC_DEVICE` | `null` | system default, a name substring, or an index |
| `PASTE` | `true` | `false` is clipboard only |
| `TRAILING_SPACE` | `true` | append a space so dictations do not run together |
| `OVERLAY` | `true` | `false` is silent mode |
| `MIN_PEAK` | `0.025` | energy gate; **re-measure on a new machine** |
| `SILENT_PEAK` | `0.0005` | below this the mic returned silence, not a quiet room |
| `KEEP_WARM_SEC` | `300` | silent inference interval while idle; `0` disables |
| `AUDIO_CTX` | `640` | encoder window in 20 ms frames (640 = 12.8 s) |
| `THREADS` | `4` | performance cores on this chip |

## Permissions

Three, and the app cannot grant itself any of them:

- **Microphone** — capture. Without the usage string in `Info.plist`, macOS kills
  the process instead of returning an error.
- **Accessibility** — the event tap and the Command-V. Granted per *code
  identity*: a source run is the Python binary, a bundle is `Nemo.app`. Expect to
  grant it once per identity, not once per rebuild if the signing identity is
  stable.
- **Input Monitoring** — some macOS versions want this for the tap as well. If
  Accessibility is on and the hotkey still does nothing, check here.

**Check permissions** in the menu says which is missing and opens the right pane.

Dictation into a **secure input field** (password boxes) does not work. macOS
blocks every tap there. That is correct behaviour, not a bug.

## What the Mac build does differently

Measured on this machine, not assumed:

1. **The engine window is a server setting, not a request field.** whisper.cpp
   accepts `audio_ctx` per request, but on this build varying it between requests
   corrupts the next decode (deterministically: a smaller window after a larger
   one produced garbage). So the window is fixed at server start (`AUDIO_CTX`),
   and a take longer than the window restarts the server larger once.
2. **A smaller window is not free.** Even when the window covers the audio, a
   640-frame window transcribed a 10.8 s clip correctly while 768 produced a
   duplicated sentence and 900 mangled words on the same audio. Quality needs the
   window to match the model's expectations, so the default is a measured
   compromise, not the smallest value that avoids truncation.
3. **The vocabulary prompt is positional.** Terms about four tokens from the end
   of the prompt have no effect; the last two or three decide the spelling. This
   build repeats the first three terms at the end so the ones listed first are
   the ones that land. Put the names that matter at the top of `vocabulary.txt`.
4. **Beam search is not the cost.** Greedy decoding measured identical at full
   window; it is kept for determinism.
5. **The encoder, not the decoder, is the latency.** large-v3-turbo keeps
   Whisper's full 32-layer encoder: 490 ms on Metal for the 30 s window against
   100 ms for `small.en`. That is why `AUDIO_CTX` exists.

## Measured here

Turbo, Metal, warm server, HTTP round trip:

| Window | Time (4.7 s clip) | Notes |
|---|---|---|
| 1500 (30 s) | 448 ms | the default every other build uses |
| 640 (12.8 s) | 284 ms | default here |
| 512 (10.2 s) | 181 ms | truncates 10.8 s audio |
| 256 (5.1 s) | 129 ms | only for very short takes |

CPU fallback, same clip: 8.1 s encode against 490 ms on Metal. So Metal is
genuinely doing the work; the bottle is not the bottleneck (a native source
build measured *slower*, 650 ms).

Release-to-paste will be added to this table from `nemo.log` after a week of use,
the way the Windows README does it.

## Recovery

If the app dies hard the engine can survive holding 8129:

```sh
lsof -i :8129
pkill -f whisper-server
```

## Not in this version

Spoken formatting, a microphone picker, engine swaps, cloud anything, history on
disk. Same list as Windows, same order.
