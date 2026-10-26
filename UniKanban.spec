# -*- mode: python ; coding: utf-8 -*-
# Gera dist/UniKanban/UniKanban.exe   ->   .venv\Scripts\pyinstaller UniKanban.spec --noconfirm
from PyInstaller.utils.hooks import collect_data_files

datas = [("assets/icon.ico", "assets"), ("assets/icon.png", "assets"), ("assets/check.svg", "assets")]
datas += collect_data_files("tzdata")

a = Analysis(
    ["main.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=["keyring.backends.Windows", "win32ctypes.core", "openpyxl", "tzdata"],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick",
              "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtPdf", "tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="UniKanban", console=False,
          icon="assets/icon.ico", version=None)
coll = COLLECT(exe, a.binaries, a.datas, name="UniKanban")

