# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for BidGuard standalone Windows --onedir distribution."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
FRONTEND_DIST = ROOT / "frontend" / "dist"
if not (FRONTEND_DIST / "index.html").exists():
    raise SystemExit("frontend/dist/index.html missing — run 'cd frontend && npm run build' before PyInstaller.")

icon_path = ROOT / "build" / "bidguard.ico"

pymupdf_datas, pymupdf_binaries, pymupdf_hidden = collect_all("pymupdf")

datas = [
    (str(FRONTEND_DIST), "frontend/dist"),
    *collect_data_files("docx"),
    *collect_data_files("certifi"),
    *pymupdf_datas,
]

binaries = [
    *pymupdf_binaries,
]

hiddenimports = [
    *collect_submodules("backend"),
    *collect_submodules("uvicorn"),
    *pymupdf_hidden,
    "anyio._backends._asyncio",
    "multipart",
    "python_multipart",
    "httpx",
    "openai",
    "lxml.etree",
    "lxml._elementpath",
    "openpyxl",
    "PIL.Image",
]

a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "_pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BidGuard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(icon_path) if icon_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BidGuard",
)
