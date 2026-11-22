# Nemo for Mac 0.5

The pill now shows its state as a coloured glow around clear glass instead of
colouring the glass itself.

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

Rebuild with the same signing identity to keep your Accessibility and Microphone
grants:

```sh
IDENTITY="Apple Development: Your Name (TEAMID)" ./build.sh
```

## What changed in 0.5

- **Clear glass, coloured halo.** Listening casts a soft orange glow around the
  pill, Copied green, errors red. The material itself stays clear and continues
  to follow the user's Liquid Glass setting and accessibility options.
- **Normal system ink.** Because the glass is no longer tinted, the label and
  waveform use the ordinary dynamic system colours in every state.
- **Room for the glow.** The window is padded by 28 pt and the glass view sits
  inside a container view, so the halo is not clipped and stays around the pill
  rather than the window edge.
- **New screenshots.** The hero, state sheet, social card, Open Graph image and
  settings screenshot in `docs/` were all recaptured from the live app on a
  light background.

Everything from 0.4 carries over: `THEME` with Follow system / Light / Dark, the
220 pt pill, SF Pro Medium lettering, and the solid-pill fallback. See
[0.4 notes](release-notes-v0.4.md) for the background to that work.

## Why the change

Tinting the glass was the obvious first answer, but it did not survive contact
with real desktops: regular glass ignores `tintColor` on macOS 27, clear glass
takes it as a flat block of colour, and a translucent tint went muddy over dark
content. Apple's
[Materials](https://developer.apple.com/design/human-interface-guidelines/materials)
and [Color](https://developer.apple.com/design/human-interface-guidelines/color)
guidelines ask for the material to supply the surface and for colour to be used
sparingly. A glow outside the glass keeps both: the surface is the system's own,
and the status colour is a light around it.

## Verification

- Both suites pass; tests pin the status-to-glow mapping and the window padding.
- Captured pixels around a clear centre of `(243,244,244)` read `(252,234,219)`
  orange and `(226,244,226)` green.
- The Impeccable detector reported no findings.

The pill is drawn with Pillow, so its text has resolved system colours rather
than true AppKit vibrancy. Reduce Transparency and the user's Liquid Glass
slider are left to `NSGlassEffectView`. The solid pill (`GLASS = false`) remains
the guaranteed-contrast path.

MIT — see [LICENSE](../LICENSE) and
[THIRD-PARTY-NOTICES.md](../THIRD-PARTY-NOTICES.md).
