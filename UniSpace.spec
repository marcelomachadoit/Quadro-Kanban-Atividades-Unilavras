# -*- mode: python ; coding: utf-8 -*-
# Usado por build_exe.py, que coloca UniSpace.exe + _internal/ na raiz do projeto:
#   .venv\Scripts\python.exe build_exe.py
from PyInstaller.utils.hooks import collect_data_files

datas = [("assets/icon.ico", "assets"), ("assets/icon.png", "assets"), ("assets/check.svg", "assets"),
         ("assets/knob_on.svg", "assets"), ("assets/knob_off.svg", "assets")]
datas += collect_data_files("tzdata")

a = Analysis(
    ["main.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=["keyring.backends.Windows", "win32ctypes.core", "openpyxl", "tzdata",
                   "PySide6.QtPdf"],                       # lê o PDF do Planograma (data do AVIN)
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick",
              "PySide6.QtQml", "PySide6.QtMultimedia", "tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="UniSpace", console=False,
          icon="assets/icon.ico", version=None)
coll = COLLECT(exe, a.binaries, a.datas, name="UniSpace")

