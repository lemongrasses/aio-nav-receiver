"""Settings: typed, validated, saved to ~/.aio_receiver.json (same file and keys as before 1.0)."""

from __future__ import annotations

import dataclasses
import ipaddress
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .core import protocol as P
from .core.gate import GateConfig

log = logging.getLogger(__name__)
CONFIG_PATH = Path.home() / ".aio_receiver.json"


@dataclass(frozen=True)
class Settings:
    host: str = "0.0.0.0"
    nav_port: int = 9000
    status_port: int = 0            # 0 = same port as 0x04
    status_id: int = P.STATUS_ID
    allowed_from: str = ""          # "" = any sender
    status_timeout: float = 3.0
    ready_stable: float = 2.0
    nav_max_age: float = 0.5
    record_dir: str = ""            # "" = next to the executable (see osutil.default_record_dir)
    record_csv: bool = True
    alert_sound: bool = True        # sound when the output stops being usable
    show_track: bool = True

    @property
    def ports(self) -> List[int]:
        return sorted({self.nav_port, self.status_port or self.nav_port})

    def gate_config(self, use_source_filter: bool = True) -> GateConfig:
        return GateConfig(self.status_id, (self.allowed_from or None) if use_source_filter else None,
                          self.status_timeout, self.ready_stable, self.nav_max_age)

    def replace(self, **changes: Any) -> Settings:
        return dataclasses.replace(self, **changes)


# --------------------------------------------------------------- validation
def _ipv4(v: Any) -> str:
    try:
        return str(ipaddress.IPv4Address(str(v).strip()))
    except ValueError:
        raise ValueError(f"{v!r} 不是 IPv4 位址") from None


def _port(lo: int) -> Callable[[Any], int]:
    def parse(v: Any) -> int:
        p = int(str(v).strip() or 0)
        if not lo <= p <= 65535:
            raise ValueError(f"埠號要在 {lo}–65535")
        return p
    return parse


def _msg_id(v: Any) -> int:
    i = v if isinstance(v, int) else int(str(v).strip(), 0)
    if not 0 <= i <= 255 or i == P.NAV_ID:
        raise ValueError("message ID 要在 0x00–0xFF，且不能是 0x04")
    return i


def _seconds(lo: float, allow_zero: bool) -> Callable[[Any], float]:
    def parse(v: Any) -> float:
        x = float(str(v).strip())
        if not (lo <= x <= 60.0) or (x == 0 and not allow_zero):
            raise ValueError("秒數要大於 0 且不超過 60" if not allow_zero else "秒數要在 0–60")
        return x
    return parse


def _bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"{v!r} 不是 true / false")


PARSERS: Dict[str, Callable[[Any], Any]] = {
    "host": _ipv4,
    "nav_port": _port(1),
    "status_port": _port(0),
    "status_id": _msg_id,
    "allowed_from": lambda v: _ipv4(v) if str(v).strip() else "",
    "status_timeout": _seconds(0.0, False),
    "ready_stable": _seconds(0.0, True),
    "nav_max_age": _seconds(0.0, False),
    "record_dir": lambda v: str(v).strip(),
    "record_csv": _bool,
    "alert_sound": _bool,
    "show_track": _bool,
}


def parse_field(name: str, value: Any) -> Any:
    """Validate one field; raises ValueError with a message for the user."""
    return PARSERS[name](value)


def from_dict(raw: Dict[str, Any]) -> Tuple[Settings, List[str]]:
    """Settings from a JSON object. A bad or missing field keeps its default; problems are listed."""
    values: Dict[str, Any] = {}
    problems: List[str] = []
    for name in PARSERS:
        if name not in raw:
            continue
        try:
            values[name] = parse_field(name, raw[name])
        except (ValueError, TypeError) as e:
            problems.append(f"{name}: {e}")
    return Settings(**values), problems


def to_dict(s: Settings) -> Dict[str, Any]:
    d = dataclasses.asdict(s)
    d["status_id"] = f"0x{s.status_id:02X}"
    return d


def load(path: Optional[Path] = None) -> Tuple[Settings, List[str]]:
    path = path or CONFIG_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Settings(), []
    except (OSError, ValueError) as e:
        log.warning("settings file %s unreadable: %s", path, e)
        return Settings(), [f"{path.name}: {e}"]
    if not isinstance(raw, dict):
        return Settings(), [f"{path.name}: 不是 JSON 物件"]
    s, problems = from_dict(raw)
    for p in problems:
        log.warning("setting ignored: %s", p)
    return s, problems


def save(s: Settings, path: Optional[Path] = None) -> None:
    """Write atomically (temp file + rename), so a crash never leaves half a settings file."""
    path = path or CONFIG_PATH
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(to_dict(s), indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
