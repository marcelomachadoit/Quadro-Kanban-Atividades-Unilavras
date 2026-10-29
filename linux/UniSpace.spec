# -*- mode: python ; coding: utf-8 -*-
# Usado por build_linux.py (precisa rodar no Linux: o PyInstaller não gera executável para outro sistema):
#   .venv/bin/python build_linux.py
from PyInstaller.utils.hooks import collect_data_files

datas = [("assets/icon.png", "assets"), ("assets/check.svg", "assets"),
         ("assets/knob_on.svg", "assets"), ("assets/knob_off.svg", "assets"),
         ("assets/fonts/MaterialIconsOutlined-Regular.otf", "assets/fonts")]
datas += collect_data_files("tzdata")

a = Analysis(
    ["main.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=["keyring.backends.SecretService", "keyring.backends.kwallet", "secretstorage", "jeepney",
                   "openpyxl", "tzdata",
                   "PySide6.QtPdf"],                       # lê o PDF do Planograma (data do AVIN)
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick",
              "PySide6.QtQml", "PySide6.QtMultimedia", "tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="UniSpace", console=False, strip=False)
coll = COLLECT(exe, a.binaries, a.datas, name="UniSpace")
