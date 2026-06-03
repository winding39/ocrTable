# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 目录模式打包 — OCR 表格识别桌面版。"""
from PyInstaller.utils.hooks import collect_all, collect_data_files

cv2_datas, cv2_binaries, cv2_hiddenimports = collect_all("cv2")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=cv2_binaries,
    datas=cv2_datas,
    hiddenimports=cv2_hiddenimports
    + [
        "PyQt5.sip",
        "PyQt5.QtPrintSupport",
        "config",
        "ocr",
        "ocr.bailian",
        "utils",
        "utils.camera",
        "utils.excel_export",
        "utils.history",
        "ui",
        "ui.styles",
        "ui.main_window",
        "ui.pages",
        "ui.pages.capture_page",
        "ui.pages.settings_page",
        "ui.pages.history_page",
        "dotenv",
        "openpyxl",
        "openpyxl.cell",
        "openpyxl.styles",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "flask"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ocrTable",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
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
    name="ocrTable",
)
