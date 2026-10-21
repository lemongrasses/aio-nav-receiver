# PyInstaller spec for all three systems:   pyinstaller --noconfirm --clean packaging/aio_receiver.spec
#   Windows  dist/AIO_NAV_Receiver.exe            one file
#   Linux    dist/aio-nav-receiver                one file
#   macOS    dist/AIO NAV Receiver.app            app bundle (one-file apps are deprecated on macOS)
# -*- mode: python ; coding: utf-8 -*-
import re
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "src/aio_receiver/__init__.py").read_text()).group(1)
NAME = {"win32": "AIO_NAV_Receiver", "darwin": "AIO NAV Receiver"}.get(sys.platform, "aio-nav-receiver")
MAC = sys.platform == "darwin"

a = Analysis(
    [str(ROOT / "packaging/entry.py")],
    pathex=[str(ROOT / "src")],
    excludes=["pytest", "mypy", "ruff", "unittest", "pydoc", "doctest"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if MAC:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=False, upx=False,
              argv_emulation=False)
    coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)
    app = BUNDLE(
        coll,
        name=f"{NAME}.app",
        bundle_identifier="tw.aionav.receiver",
        version=VERSION,
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            # macOS 15+: asked once before the app may receive from devices on the local network
            "NSLocalNetworkUsageDescription": "接收 AIO NAV 裝置送來的 UDP 導航與狀態封包。",
        },
    )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=NAME, console=False, upx=False,
              runtime_tmpdir=None, disable_windowed_traceback=False)
