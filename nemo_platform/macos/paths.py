"""Where Nemo keeps its files on a Mac.

A .app can be replaced wholesale, so nothing user-owned lives inside the bundle.
Source runs and the frozen app share one directory, which is also where the
model was staged.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def data_dir() -> Path:
    path = Path.home() / "Library" / "Application Support" / "Nemo"
    path.mkdir(parents=True, exist_ok=True)
    (path / "models").mkdir(exist_ok=True)
    return path


def server_exe() -> Path:
    """whisper-server from Homebrew.

    Deliberately not bundled: the binary links libwhisper and the ggml dylibs by
    @rpath, so a plain copy cannot load (measured: "Library not loaded:
    @rpath/libwhisper.1.dylib"). Bundling properly needs install_name_tool on the
    whole dependency tree. For a single machine with `brew install whisper.cpp`,
    depending on it is the smaller lie.
    """
    for candidate in (
        Path("/opt/homebrew/bin/whisper-server"),
        Path("/usr/local/bin/whisper-server"),
    ):
        if candidate.exists():
            return candidate
    found = shutil.which("whisper-server")
    if found:
        return Path(found)
    return Path("/opt/homebrew/bin/whisper-server")


def app_bundle() -> Path | None:
    """The .app we would launch at login, if one has been built."""
    if getattr(sys, "frozen", False):
        # Contents/MacOS/Nemo -> Nemo.app
        return Path(sys.executable).resolve().parents[2]
    here = Path(__file__).resolve().parents[2]
    for candidate in (
        Path.home() / "Applications" / "Nemo.app",
        here / "dist" / "Nemo.app",
    ):
        if candidate.exists():
            return candidate
    return None
