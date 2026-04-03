# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Mass Torrent Loader
# Build with: pyinstaller build.spec

a = Analysis(
    ['mass_torrent_loader.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['qbittorrentapi'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MassTorrentLoader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)
