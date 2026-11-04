#!/bin/bash
# Build Nemo.app from a clean checkout. arm64 only: it is one machine.
set -euo pipefail
cd "$(dirname "$0")"

IDENTITY="${IDENTITY:-Apple Development: Alan Soon (KF8DGTVPW3)}"
APP="dist/Nemo.app"

echo "==> virtualenv"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements-macos.txt

echo "==> icon"
.venv/bin/python make_icon.py >/dev/null 2>&1 || true
if [ -f nemo.png ]; then
  rm -rf Nemo.iconset && mkdir Nemo.iconset
  for size in 16 32 64 128 256 512; do
    sips -z $size $size nemo.png --out "Nemo.iconset/icon_${size}x${size}.png" >/dev/null
    d=$((size*2))
    sips -z $d $d nemo.png --out "Nemo.iconset/icon_${size}x${size}@2x.png" >/dev/null
  done
  iconutil -c icns Nemo.iconset -o nemo.icns
fi

echo "==> pyinstaller"
rm -rf build dist
.venv/bin/pyinstaller --noconfirm --windowed --name Nemo \
  --osx-bundle-identifier sg.fractals.nemo \
  ${ICON:+--icon "$ICON"} \
  --hidden-import nemo_platform.macos.pill \
  --hidden-import nemo_platform.macos.menubar \
  --hidden-import nemo_platform.macos.hotkey \
  --hidden-import nemo_platform.macos.paste \
  --hidden-import nemo_platform.macos.permissions \
  --hidden-import nemo_platform.macos.login \
  --hidden-import nemo_platform.macos.dialog \
  --hidden-import nemo_platform.macos.power \
  --target-arch arm64 --distpath dist nemo.py

PLIST="$APP/Contents/Info.plist"
echo "==> Info.plist"
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :LSUIElement true" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :NSMicrophoneUsageDescription string 'Nemo records while you hold Right Option, and transcribes on this Mac.'" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :NSMicrophoneUsageDescription 'Nemo records while you hold Right Option, and transcribes on this Mac.'" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string 0.2" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString 0.2" "$PLIST"

echo "==> engine"
# Homebrew's, not bundled: whisper-server links libwhisper and the ggml dylibs by
# @rpath, so a copy inside the bundle cannot load without install_name_tool on the
# whole tree. brew install whisper.cpp is the runtime dependency.
if ! command -v whisper-server >/dev/null; then
  echo "!! whisper-server not found: brew install whisper.cpp" >&2
fi

echo "==> sign (no hardened runtime: not notarising, and it fights PyInstaller's dylibs)"
codesign --force --deep --sign "$IDENTITY" "$APP"

echo "==> wrapper"
mkdir -p bin
printf '#!/bin/sh\nexec "%s/Contents/MacOS/Nemo" "$@"\n' "$PWD/$APP" > bin/nemo
chmod +x bin/nemo
ln -sf "$PWD/bin/nemo" /opt/homebrew/bin/nemo 2>/dev/null || true

echo
echo "built $APP"
codesign -dv "$APP" 2>&1 | grep -E "Authority|TeamIdentifier" || true
echo "run: open $APP    (or ./bin/nemo --status)"
echo "NOTE: needs Homebrew's whisper.cpp at runtime: brew install whisper.cpp"
