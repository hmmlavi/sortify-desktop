# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for Sortify standalone desktop distribution."""

from pathlib import Path
import sys

block_cipher = None
ROOT_DIR = Path(SPECPATH).resolve()
IS_WINDOWS = sys.platform.startswith("win")

datas = [
    (str(ROOT_DIR / "assets"), "assets"),
    (str(ROOT_DIR / "LICENSE"), "."),
]

hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtSvg",
    "pypdf",
    "docx",
    "pptx",
    "openpyxl",
    "PIL",
    "PIL.Image",
    "keyring",
    "keyring.backends",
    "sqlite3",
]

if IS_WINDOWS:
    hiddenimports.append("keyring.backends.Windows")

excludes = [
    "pytest",
    "_pytest",
    "pip",
    "setuptools",
    "wheel",
    "tkinter",
    "PySide6.QtWebEngine",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
]

a = Analysis(
    [str(ROOT_DIR / "main.py")],
    pathex=[str(ROOT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

version_file = str(ROOT_DIR / "packaging" / "windows_version_info.txt") if IS_WINDOWS else None
icon_file = str(ROOT_DIR / "assets" / "sortify.ico")

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Sortify",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=version_file,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Sortify",
)
