"""Per-OS details: folders, log file, firewall hint, Windows DPI and console."""

from __future__ import annotations

import logging
import logging.handlers
import os
import socket
import sys
import tempfile
from pathlib import Path
from typing import List, NamedTuple, Optional, Sequence

from . import APP_NAME, i18n

WINDOWS, MACOS = sys.platform == "win32", sys.platform == "darwin"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def executable_dir() -> Path:
    """Folder of the portable executable; the working folder when run from source."""
    return Path(sys.executable).resolve().parent if is_frozen() else Path.cwd()


def _writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=folder):
            pass
        return True
    except OSError:
        return False


def default_record_dir() -> Path:
    """logs/ next to the executable, so a USB stick carries its recordings with it.

    Inside a macOS .app bundle, or on a read-only medium, Documents/AIO NAV Receiver/logs instead.
    """
    here = executable_dir() / "logs"
    if ".app/Contents/" not in here.as_posix() and _writable(here):
        return here
    return Path.home() / "Documents" / APP_NAME / "logs"


def record_dir(configured: str) -> Path:
    return Path(configured).expanduser() if configured else default_record_dir()


def log_dir() -> Path:
    if WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
    if MACOS:
        return Path.home() / "Library" / "Logs" / APP_NAME
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "aio-nav-receiver"


def setup_logging(verbose: bool = False) -> Optional[Path]:
    """Application log (not the recordings): rotating, 3 x 1 MB. Returns its path, or None."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    path = log_dir() / "app.log"
    h: logging.Handler
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        h = logging.handlers.RotatingFileHandler(path, maxBytes=1 << 20, backupCount=3, encoding="utf-8")
    except OSError:
        h = logging.NullHandler()
    h.setFormatter(fmt)
    root.addHandler(h)
    if sys.stderr is not None:
        s = logging.StreamHandler()
        s.setFormatter(fmt)
        s.setLevel(logging.WARNING)
        root.addHandler(s)
    return path if isinstance(h, logging.handlers.RotatingFileHandler) else None


def local_ipv4() -> List[str]:
    """This computer's IPv4 addresses (for the "set output_udp to this PC" step); loopback excluded."""
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return []
    ips = {str(i[4][0]) for i in infos if not str(i[4][0]).startswith(("127.", "169.254."))}
    # Ordinary LAN / Wi-Fi addresses first; VPN and virtual adapters (100.x, 172.x) after.
    rank = {"192.168.": 0, "10.": 1, "172.": 2}
    return sorted(ips, key=lambda ip: (next((r for p, r in rank.items() if ip.startswith(p)), 3), ip))


class FirewallHint(NamedTuple):
    text: str
    command: Optional[str]          # copied by the button; None = nothing to copy on this OS


def firewall_hint(ports: Sequence[int]) -> FirewallHint:
    plist = ",".join(str(p) for p in ports)
    if WINDOWS:
        return FirewallHint(i18n.t("fw.windows"),
                            f'New-NetFirewallRule -DisplayName "AIO NAV UDP" -Direction Inbound -Protocol UDP '
                            f"-LocalPort {plist} -Action Allow")
    if MACOS:
        return FirewallHint(i18n.t("fw.macos"), None)
    return FirewallHint(i18n.t("fw.linux"), " && ".join(f"sudo ufw allow {p}/udp" for p in ports))


def firewall_copied_text() -> str:
    return i18n.t("fw.copied_windows" if WINDOWS else "fw.copied_other")


def enable_dpi_awareness() -> None:
    if sys.platform != "win32":     # spelled out so mypy skips the rest on other systems
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def attach_console() -> None:
    """Windowed Windows build: print command-line output into the console that started it."""
    if sys.platform != "win32" or not is_frozen() or sys.stdout is not None:
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        if k32.AttachConsole(-1):
            # CONOUT$ is a console device: Python writes it with WriteConsoleW from UTF-8 (PEP 528),
            # so Chinese shows correctly whatever the console code page is.
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")  # noqa: SIM115
            sys.stderr = sys.stdout
    except (AttributeError, OSError):
        pass
