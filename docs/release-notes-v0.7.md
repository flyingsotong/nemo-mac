# Nemo for Mac 0.7

A long dictation no longer makes the next sentence slow.

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
This release needs **whisper.cpp 1.9.6 or later**; earlier versions garble the
next transcription when the encoder window changes.

Rebuild with the same signing identity to keep your Accessibility and Microphone
grants:

```sh
IDENTITY="Apple Development: Your Name (TEAMID)" ./build.sh
```

## What changed in 0.7

Each dictation now asks the engine for exactly the encoder window it needs —
from about 2.5 seconds for a short take up to the full 30 seconds for a long
one. Previously the window was a server-wide setting: a long take or a decoder
loop shut the engine down and started it again with a bigger window, which cost
about a second, and every later take stayed slow until a 90-second idle reset.

Now the retry at the full window is just one request. The next sentence goes
straight back to its own window. The startup window remains 640 frames, and the
90-second reset and its restart are gone.

The log reports the window each take actually used, so a `win=` value of 1500
means this take needed the full window, not that the engine is stuck there.

Everything from 0.6 carries over, including the key-down warm-up.

## Why it changed

whisper.cpp 1.9.6 fixed flash attention attending to padded K/V rows. On 1.9.5,
changing `--audio-ctx` between requests left stale values in those rows and
deterministically corrupted the next decode — which is why Nemo had to restart
the whole engine to change the window. The fix was verified on this Mac: an
isolated server on 1.9.6 was sent windows of 1500, 340, 250, 640 and 1500 in
sequence, and every transcription came back clean.

## Verification

- Both suites pass, including four new tests that assert a loop retry asks for a
  bigger window without calling `ensure()` — the restart path no longer exists.
- The real `--file` path transcribed a 3-second clip with a per-request window
  and shut the engine down cleanly.
- Rebuilt and signed with the same Apple Development identity, so TCC grants
  survive. The bundle reports 0.7 in both the app and `Info.plist`.

MIT — see [LICENSE](../LICENSE) and
[THIRD-PARTY-NOTICES.md](../THIRD-PARTY-NOTICES.md).
