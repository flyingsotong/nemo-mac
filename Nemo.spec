# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['nemo.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['nemo_platform.macos.pill', 'nemo_platform.macos.menubar', 'nemo_platform.macos.hotkey', 'nemo_platform.macos.paste', 'nemo_platform.macos.permissions', 'nemo_platform.macos.login', 'nemo_platform.macos.dialog', 'nemo_platform.macos.power'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Nemo',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='arm64',
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Nemo',
)
app = BUNDLE(
    coll,
    name='Nemo.app',
    icon=None,
    bundle_identifier='sg.fractals.nemo',
)
