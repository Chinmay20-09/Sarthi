# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Sarthi Desktop client.

Builds ``Desktop/sarthi.exe`` — a windowed (no console) one-file
executable that launches the SARTHI textbox GUI.

Build (from the repository root):

    pyinstaller Desktop/sarthi_client.spec --noconfirm --distpath Desktop/dist
    copy Desktop\\dist\\sarthi.exe Desktop\\sarthi.exe

The exe is a build artifact (gitignored); this spec is the source of
truth for how it is produced.
"""

import sys
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()          # Desktop/
CLIENT_DIR = SPEC_DIR / "client"             # Desktop/client/
REPO_ROOT = SPEC_DIR.parent                  # Sarthi/

block_cipher = None


a = Analysis(
    [str(SPEC_DIR / "run.py")],
    pathex=[str(CLIENT_DIR), str(REPO_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # The client is a thin HTTP shell — keep the bundle lean and
        # prove it needs none of the backend stack.
        "brain",
        "knowledge",
        "skills",
        "hermes",
        "speech",
        "hands",
        "connectors",
        "database",
        "events",
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="sarthi",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # windowed app — no console window on launch
    icon=None,
)
