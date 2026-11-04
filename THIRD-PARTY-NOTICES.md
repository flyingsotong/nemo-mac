# Third-party notices

Nemo for Mac is MIT licensed; see `LICENSE`. It uses other people's work, and
those components keep their own licences.

There are **no LGPL dependencies** in this build, because the two that existed in
the Windows version have native replacements: the hotkey is a `CGEventTap` instead
of `pynput`, and the menu bar item is an `NSStatusItem` instead of `pystray`.

## The engine — installed, not redistributed

| Component | Licence | Source |
|---|---|---|
| whisper.cpp (`whisper-server`, `whisper-cli`, `libwhisper`) | MIT | <https://github.com/ggerganov/whisper.cpp> |
| ggml | MIT | <https://github.com/ggml-org/ggml> |

`build.sh` does not bundle the engine: `whisper-server` links `libwhisper` and the
ggml dylibs by `@rpath`, so a copy inside a `.app` cannot load without
`install_name_tool` over the whole dependency tree. `brew install whisper.cpp`
installs it instead, and Nemo depends on it at runtime.

## Python packages in `Nemo.app`

| Package | Licence | Source |
|---|---|---|
| Python | PSF-2.0 | <https://python.org> |
| numpy | BSD-3-Clause | <https://numpy.org> |
| Pillow | MIT-CMU | <https://python-pillow.org> |
| sounddevice | MIT | <https://python-sounddevice.readthedocs.io> |
| pyobjc (Cocoa, Quartz, AVFoundation, ApplicationServices) | MIT | <https://pyobjc.readthedocs.io> |
| PyInstaller (build tool only) | GPLv2 with the bootloader exception, which permits distributing non-free bundled programs | <https://pyinstaller.org> |

## The speech model

Not distributed here. `--fetch-model` downloads it from
<https://huggingface.co/ggerganov/whisper.cpp>, and those ggml conversions are the
MIT-licensed OpenAI Whisper weights.
