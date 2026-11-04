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
2. **A small window can make the decoder repeat a sentence.** At 640 frames one
   clip transcribed correctly and another came back doubled; at 768 it was the
   other way round. No small window was clean on both. So the transcript is
   checked for a repeated run of eight words, and a hit retries once at the full
   1500-frame window and stays there for the session. A doubled sentence in a
   document is worse than a slower take.
3. **The vocabulary prompt is positional.** Terms about four tokens from the end
   of the prompt have no effect; the last two or three decide the spelling. This
   build repeats the first three terms at the end so the ones listed first are
   the ones that land. Put the names that matter at the top of `vocabulary.txt`.
4. **Beam search is not the cost.** Greedy decoding measured identical at full
   window; it is kept for determinism.
5. **The encoder, not the decoder, is the latency.** large-v3-turbo keeps
   Whisper's full 32-layer encoder: 490 ms on Metal for the 30 s window against
   100 ms for `small.en`. That is why `AUDIO_CTX` exists.

## Cost of being idle

The spec asks whether a hidden app is indistinguishable from not running. Measured
with `ps` over 90 s with the pill hidden and one keep-warm in the window:

| Process | CPU time | Share of one core | Resident |
|---|---|---|---|
| `Nemo` | 0.20 s / 90 s | ~0.2% | 105 MB, unchanged |
| `whisper-server` | 0.33 s / 90 s | ~0.4% | 1.8 GB, unchanged |

Extrapolated, that is single-digit seconds of CPU per hour, of which most is the
keep-warm inference (one every 300 s on AC, stretched on battery). The pill runs
no timer while hidden, which is the design the spec asked for, and both
resident sizes were identical at both samples, so nothing is drifting.

`powermetrics` would give joules rather than CPU time, but it needs root; these
numbers are the honest proxy, not the spec's ideal.

## Pill frame cost
`render()` measured at 30 Hz over 120 frames:

| Scale | Median | p90 |
|---|---|---|
| 1x (Windows equivalent) | 0.55 ms | 0.63 ms |
| 2x (this Retina display) | 2.08 ms | 2.26 ms |

The spec's target is under 2 ms; at 2x it is just over, against 1.69 ms on
Windows at 1x. That is 6% of one core while the pill is visible, which is the only
time it renders, so it has not been optimised further — the visible cost is about
one second per dictation.

## Cold start

Measured on the signed bundle, from the launch to the menu-bar item being usable:
**1.10 s** (the spec's target is under 2 s).

The order in the log matters more than the number: the event tap installs and the
listener comes up *before* the engine is asked to warm, so a press during startup
queues behind the engine instead of being dropped for want of a hook.

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

Release-to-paste, driven end to end through the microphone with the clipboard as
the only output (speaker playback, synthetic Right Option, so the timing excludes
human key travel and the paste keystroke):

| Take | Audio | Engine | Output | Total | Peak |
|---|---|---|---|---|---|
| push | 6.0 s | 323 ms | 4 ms | 328 ms | 0.110 |
| toggle | 5.5 s | 318 ms | 3 ms | 321 ms | 0.118 |

The output half is 3-4 ms, matching the Windows measurement. The engine half is
what the product feels like, and it is why `AUDIO_CTX` exists.

First inference after start measured **797 ms**, and the keep-warm logged itself
absorbing it (`keep-warm absorbed a cold take`) before anyone was waiting. That is
the week-one hypothesis behaving as designed, on a second platform.

## Acceptance status

Verified here: the tap (swallow, press/release, re-arm), recording, the gate
(including that it learns: quiet peaks loosened it to 0.0098, floored at 0.002),
transcription, the clipboard, **the whole pipeline into a focused TextEdit
document**, Escape cancel, toggle mode, all eight pill states, the menu bar item
and its wording, **Insert last transcript**, pause and resume with the icon dimmed,
Check permissions, the signed bundle surviving a rebuild with its Accessibility
grant intact, the login item, and clean shutdown.

Needs a human: a real keypress end to end (the pill's **Paused** on a press while
paused, and Option reaching the document while paused), Copy last transcript by
clicking, sleep/wake, and `MIN_PEAK` against a real voice.

## Tests

Two suites pin the behaviour that came out of measurement, so retuning a constant
cannot quietly change what the app promises:

```sh
.venv/bin/python scripts/test_hotkey_logic.py   # what the tap swallows and passes
.venv/bin/python scripts/test_core_logic.py     # gate, loop detection, window, filter, vocabulary
```

`test_hotkey_logic.py` asserts the central promise directly: Right Option is
swallowed while running, reaches the app while paused, is never swallowed with
`SUPPRESS_HOTKEY: false`, left Option is never touched, and Escape is observed but
passed through.

## Recovery

If the app is killed hard (not Quit), the engine can survive holding 8129. The
next start adopts it, logs that the window is unknown, and treats it as the
configured default; a longer take restarts it with a window it knows. Quitting
from the menu stops an adopted engine too.

```sh
lsof -i :8129
pkill -f whisper-server
```

## Not in this version

Spoken formatting, a microphone picker, engine swaps, cloud anything, history on
disk. Same list as Windows, same order.
