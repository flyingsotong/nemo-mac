# Nemo for Mac 0.6

The first take after a break is as fast as any other.

Hold **Right Command**, speak, let go. Whisper runs on Metal through a resident
`whisper-server`, the text lands where your cursor is, and audio never leaves the
machine.

## Install

```sh
brew install whisper.cpp          # the Metal engine; not bundled
git clone https://github.com/flyingsotong/nemo-mac && cd nemo-mac
./build.sh                        # builds and signs dist/Nemo.app
open dist/Nemo.app
```

The model (1.6 GB, `large-v3-turbo`) is fetched and SHA-256 verified on first run.

Rebuild with the same signing identity to keep your Accessibility and Microphone
grants:

```sh
IDENTITY="Apple Development: Your Name (TEAMID)" ./build.sh
```

## What changed in 0.6

After 60 seconds idle, pressing the hotkey now starts a silent 0.2-second
inference in the background while the microphone opens. The GPU is awake by the
time you finish speaking, so the first take after a gap no longer pays the
cold-start cost.

This matters most on battery. `KEEP_WARM_SEC` is deliberately stretched to 15
minutes there to save power, which left a window where the first dictation after
a break cost around 460 ms. The warm-up now happens during the press instead,
and the periodic keep-warm is unchanged.

The new log line is `key-down warm`; on a warm take it reads `key-down warm
257ms`, or `key-down warm absorbed a cold take` if it caught a fully cold engine.
It is a background thread, so the event tap never waits on it.

Everything from 0.5 carries over: clear glass with a coloured glow, `THEME`
with Follow system / Light / Dark, the 220 pt pill, and the solid-pill fallback.

## Why it changed

A hardware review of the three-week `nemo.log` found that the median take at the
normal 640-frame window was already 248 ms, and the output half was 1–4 ms.
The one remaining hiccup in daily use was the first take after a long idle, not
the steady-state path. Warming on the timer alone meant either paying that cost
or waking the GPU every five minutes on battery. Warming on the press costs
nothing when the app is idle and hides the delay inside the time you spend
speaking.

The larger structural win — per-request encoder windows, which would remove the
one-second engine restart on a long take — is blocked on a whisper.cpp fix that
has not reached Homebrew yet. It was deliberately left out of this release.

## Verification

- Both suites pass: `scripts/test_core_logic.py` and `scripts/test_hotkey_logic.py`.
- Live log on 26 Nov: `key-down warm 257ms`, then takes at 231 ms and 241 ms,
  against ~460 ms after a comparable idle before the change.
- Rebuilt and signed with the same Apple Development identity, so TCC grants
  survive. Event tap and engine came up cleanly on relaunch.
- The helper's default log lines are byte-identical, so existing keep-warm
  history stays comparable.

MIT — see [LICENSE](../LICENSE) and
[THIRD-PARTY-NOTICES.md](../THIRD-PARTY-NOTICES.md).
