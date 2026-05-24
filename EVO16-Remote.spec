# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for EVO 16 Remote standalone macOS binary."""

import os
from pathlib import Path

PROJECT_ROOT = Path(SPECPATH).parent

a = Analysis(
    ['backend/main.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        ('web/index.html', 'web'),
        ('web/app.js', 'web'),
        ('web/style.css', 'web'),
        ('mac-evo16/mac-evo16', 'mac-evo16'),
    ],
    hiddenimports=['fastapi', 'uvicorn', 'pydantic', 'starlette'],
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
    a.binaries,
    a.datas,
    [],
    name='EVO16-Remote',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

app = BUNDLE(
    exe,
    name='EVO16-Remote.app',
    icon=None,
    bundle_identifier='com.david.evo16-remote',
    version='1.0.0',
    info_plist={
        'CFBundleName': 'EVO 16 Remote',
        'CFBundleDisplayName': 'EVO 16 Remote',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'LSMinimumSystemVersion': '14.0',
        'NSHighResolutionCapable': True,
    },
)
