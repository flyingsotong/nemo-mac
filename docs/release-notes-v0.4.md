# Nemo for Mac 0.4

A real light/dark appearance, and a pill that looks and behaves like macOS 27.

Hold **Right Command**, speak, let go. Whisper runs on Metal through a resident
whisper-server, the text lands where your cursor is, and audio never leaves the
machine.

## Install

```sh
brew install whisper.cpp          # the Metal engine; not bundled
git clone https://github.com/flyingsotong/nemo-mac && cd nemo-mac
./build.sh                        # builds and signs dist/Nemo.app
open dist/Nemo.app
```

The model (1.6 GB, `large-v3-turbo`) is fetched and SHA-256 verified on first run.
macOS 26 or later is needed for Liquid Glass; earlier versions use the painted
pill.

Accessibility and Microphone grants are tied to the code identity. Rebuild with
the same signing identity, for example:

```sh
IDENTITY="Apple Development: Your Name (TEAMID)" ./build.sh
```

## Appearance

**Menu → Settings… → General → Appearance** has three choices:

| Choice | Meaning |
|---|---|
| Follow system | default; Nemo follows the macOS light/dark setting live |
| Light | pin the light appearance |
| Dark | pin the dark appearance |

The same value is `THEME` in `config.json`, where `"system"`, `"light"` and
`"dark"` are accepted. An invalid value falls back to following the system.

The Settings window and other AppKit surfaces take the same appearance as the
pill. Changing the system appearance while Nemo is running repaints the pill
without a restart.

## The pill

- **No fixed palette in glass mode.** `NSGlassEffectView` supplies the surface,
  so it follows the user's Liquid Glass setting, the content behind it, and
  Reduce Transparency and Increase Contrast.
- **System ink.** The label, waveform and status colours are resolved from
  dynamic AppKit colours (`labelColor`, `secondaryLabelColor` and the system
  status colours) under the current appearance. The pill no longer freezes a
  hand-picked palette into the image.
- **Status colour.** Listening tints the whole material orange, Copied green,
  errors red. The tint is translucent — it is coloured glass, not a block of
  paint. Quiet states return to the plain material.
- **Narrower and quieter.** 220 pt wide instead of 252. The dot is gone; the
  waveform is the live signal, and the label sits at the left inset with room
  around it.
- **SF Pro Medium.** The pill label uses the system face at a proper weight.
  Windows keeps Bahnschrift/Segoe UI.

Turning **Liquid Glass pill** off in Settings gives the solid painted pill. That
path is the guaranteed-contrast fallback: it has its own light, dark and Increase
Contrast surfaces.

## Why it changed

The old renderer had one dark palette. In light appearance the glass material
stayed light while the text was near-white, so the pill was unreadable. The first
fix painted a themed fill over the material and used fixed tints; that was both
opaque and contrary to Apple's guidance. The current version follows the
[Materials](https://developer.apple.com/design/human-interface-guidelines/materials)
and [Color](https://developer.apple.com/design/human-interface-guidelines/color)
guidelines: the material supplies the surface, colour is used sparingly for
status, and custom colours have accessible variants.

One macOS 27 detail worth recording: regular glass ignores `tintColor`, so the
status states switch to clear glass with a translucent system tint. Untinted
states stay on regular glass, which is more legible over arbitrary content.

## Verification

- Both test suites pass: `scripts/test_core_logic.py` and
  `scripts/test_hotkey_logic.py`.
- Every solid fallback ink/surface pair clears 4.5:1, including the Increase
  Contrast surfaces.
- Tests pin that glass mode paints no surface, that the dot is gone, that the
  tint mapping is correct, and that the tint stays translucent.
- Material behaviour was checked by capturing the live pill and sampling pixels:
  untinted glass reads `(0,0,0)` over black and `(72,72,72)` over white; the
  tinted pill reads `(242,210,182)` over a white backdrop.
- The Impeccable design detector reported no findings.

The pill is drawn with Pillow, so its text uses resolved system colours rather
than true AppKit vibrancy. Reduce Transparency and the user's Liquid Glass
slider were not exercised directly; those are handled by `NSGlassEffectView`.

## Also in 0.4

- Settings window refinements and the live microphone row carried over from 0.3.
- `build.sh` now records version 0.4 in the bundle and names the correct hotkey
  in the microphone usage description.
- All derived documentation images were regenerated from the current renderer.

MIT — see [LICENSE](../LICENSE) and
[THIRD-PARTY-NOTICES.md](../THIRD-PARTY-NOTICES.md).
