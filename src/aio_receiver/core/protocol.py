"""AIO NAV UDP packet formats: 0x04 navigation solution and 0x05 readiness status.

Both share one frame:  55 AA | msg_id u8 | payload_len u16 LE | payload | checksum u8
checksum = 8-bit sum of the bytes from msg_id to the end of the payload.
Source: web_monitor aio_system_dashboard/nav/decoder.py and nav/status_packet.py.
"""

from __future__ import annotations

import struct
from typing import NamedTuple, Optional, Sequence

SYNC = b"\x55\xAA"
NAV_ID = 0x04
STATUS_ID = 0x05
STATUS_VERSION = 1

NAV = struct.Struct("<Qdd28fH3f")          # 150 bytes
NAV_LEN = 5 + NAV.size + 1                 # 156
STATUS = struct.Struct("<BBBBIIQIIBBHHH")  # 36 bytes
STATUS_LEN = 5 + STATUS.size + 1           # 42
NAV_AGE_UNKNOWN = 0xFFFF


class NavPacket(NamedTuple):
    """One 0x04 packet. Field order is the wire order."""

    time_us: int
    lat: float
    lon: float
    height: float
    vn: float
    ve: float
    vu: float
    roll: float
    pitch: float
    heading: float                  # may arrive as -180..180; display modulo 360
    pos_n_std: float
    pos_e_std: float
    pos_d_std: float
    vel_n_std: float
    vel_e_std: float
    vel_d_std: float
    roll_std: float
    pitch_std: float
    heading_std: float
    gyro_bias_x: float
    gyro_bias_y: float
    gyro_bias_z: float
    accel_bias_x: float
    accel_bias_y: float
    accel_bias_z: float
    gyro_scale_x: float
    gyro_scale_y: float
    gyro_scale_z: float
    accel_scale_x: float
    accel_scale_y: float
    accel_scale_z: float
    flags_wire: int                 # low byte bit-reversed on the wire
    odo_scale: float
    mount_pitch: float
    mount_yaw: float

    @property
    def flags(self) -> int:
        """Flags in C-side bit order: bit i is FLAG_NAMES[i]."""
        return reverse_bits8(self.flags_wire)

    @property
    def time_s(self) -> float:
        return self.time_us / 1e6

    def has_flag(self, name: str) -> bool:
        return bool(self.flags >> FLAG_NAMES.index(name) & 1)


class StatusPacket(NamedTuple):
    """One 0x05 packet (version 1)."""

    version: int
    state: int
    action: int
    gnss_quality: int
    session: int
    sequence: int
    uptime_ms: int
    health: int
    inhibit: int
    nav_flags: int
    reserved0: int
    nav_rate_dhz: int
    nav_age_ms: int
    reserved1: int


NAV_NAMES = NavPacket._fields
STATUS_NAMES = StatusPacket._fields
NAV_F64 = frozenset({"lat", "lon"})       # the only doubles; the other floats are f32 on the wire

FLAG_NAMES = ("ZUPT", "ZIHR", "NHC", "GNSS", "VUPT", "ALIGN", "HEADING", "FINE")
AIDING_FLAGS = ("GNSS", "ZUPT", "ZIHR", "NHC", "VUPT")
ALIGN_MASK = 0b1110_0000                   # ALIGN | HEADING | FINE

STATES = ("BOOTING", "CHECKING", "NAV_STARTING", "KEEP_STILL", "MOVE_STRAIGHT", "REFINING",
          "READY", "DEGRADED", "FAULT", "MAINTENANCE")
READY = STATES.index("READY")
STATE_TEXT = {
    "BOOTING": "Dashboard 剛啟動", "CHECKING": "等待前置條件或自動啟動",
    "NAV_STARTING": "AIO NAV 已啟動，尚無有效輸出", "KEEP_STILL": "對準第 1 階段（未對準）",
    "MOVE_STRAIGHT": "對準第 2 階段（航向尚未有效）", "REFINING": "對準第 3 階段，或缺少必要條件",
    "READY": "可使用", "DEGRADED": "曾經 READY，之後失去條件或對準",
    "FAULT": "AIO NAV、其輸出或擁有權有問題", "MAINTENANCE": "已停止（操作員停止或未啟動）",
}
ACTIONS = ("NONE", "HOLD_STILL", "DRIVE_STRAIGHT", "KEEP_DRIVING", "SAFE_STOP", "SERVICE_REQUIRED",
           "MAINTENANCE_HOLD")
ACTION_TEXT = {
    "NONE": ("不需動作", "Nothing to do."),
    "HOLD_STILL": ("車輛保持完全靜止", "Keep the vehicle completely still."),
    "DRIVE_STRAIGHT": ("在安全空曠處等速直線行駛", "Drive straight at a steady speed in a safe, open area."),
    "KEEP_DRIVING": ("在有 GNSS 的地方繼續正常行駛", "Keep driving normally with GNSS available."),
    "SAFE_STOP": ("停止使用導航，依車輛安全程序處理",
                  "Stop using navigation and follow the vehicle's safety procedure."),
    "SERVICE_REQUIRED": ("需要維護", "Maintenance is needed."),
    "MAINTENANCE_HOLD": ("已停止，按「恢復」後繼續", "Stopped. Press Start to resume."),
}
GNSS_QUALITY = ("Unknown", "None", "SPP", "RTK float", "RTK fix")
HEALTH_BITS = ("DASHBOARD_OK", "CONFIG_OK", "IMU_STREAM_OK", "GNSS_STREAM_OK", "GNSS_QUALITY_OK",
               "NAV_PROCESS_OK", "NAV_OUTPUT_OK", "ALIGNMENT_OK", "HEADING_OK", "FINE_ALIGNMENT_OK",
               "DSO_OK", "EXTERNAL_ROUTE_OK", "RTK_CORRECTION_OK", "STORAGE_OK", "VEHICLE_ACK_OK",
               "TIME_SYNC_OK", "NO_DUPLICATE_PROCESS", "WIFI_OK")
INHIBIT_BITS = ("BOOT_IN_PROGRESS", "CONFIG_INVALID", "IMU_MISSING_OR_STALE", "GNSS_MISSING_OR_STALE",
                "GNSS_QUALITY_LOW", "NAV_NOT_RUNNING", "NAV_OUTPUT_STALE", "KEEP_STILL_REQUIRED",
                "MOVE_STRAIGHT_REQUIRED", "FINE_ALIGNMENT_REQUIRED", "DSO_NOT_READY", "EXTERNAL_ROUTE_DOWN",
                "RTK_CORRECTION_LOST", "STORAGE_NOT_WRITABLE", "MAINTENANCE_HOLD", "STARTUP_TIMEOUT",
                "OWNERSHIP_CONFLICT", "INTERNAL_FAULT")


def bit_names(bits: int, table: Sequence[str]) -> list[str]:
    return [n for i, n in enumerate(table) if bits >> i & 1]


def name_of(code: int, table: Sequence[str]) -> str:
    return table[code] if 0 <= code < len(table) else f"#{code}"


_REVERSED = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))


def reverse_bits8(x: int) -> int:
    return _REVERSED[x & 0xFF]


def message_id(pkt: bytes) -> Optional[int]:
    """The frame's message id, or None when the datagram does not start with the sync bytes."""
    return pkt[2] if len(pkt) >= 3 and pkt[:2] == SYNC else None


def _frame_ok(pkt: bytes, msg_id: int, total: int, payload: int) -> bool:
    return (len(pkt) == total and pkt[:2] == SYNC and pkt[2] == msg_id
            and pkt[3] | pkt[4] << 8 == payload and pkt[total - 1] == sum(pkt[2:total - 1]) & 0xFF)


def decode_nav(pkt: bytes) -> Optional[NavPacket]:
    if not _frame_ok(pkt, NAV_ID, NAV_LEN, NAV.size):
        return None
    return NavPacket._make(NAV.unpack_from(pkt, 5))


def decode_status(pkt: bytes, msg_id: int = STATUS_ID) -> Optional[StatusPacket]:
    if not _frame_ok(pkt, msg_id, STATUS_LEN, STATUS.size):
        return None
    s = StatusPacket._make(STATUS.unpack_from(pkt, 5))
    return s if s.version == STATUS_VERSION else None


def frame(msg_id: int, payload: bytes) -> bytes:
    head = SYNC + bytes([msg_id]) + struct.pack("<H", len(payload))
    return head + payload + bytes([sum(head[2:] + payload) & 0xFF])


def pack_nav(n: NavPacket) -> bytes:
    return frame(NAV_ID, NAV.pack(*n))


def encode_nav(time_s: float, lat: float, lon: float, height: float = 0.0, vn: float = 0.0, ve: float = 0.0,
               vu: float = 0.0, roll: float = 0.0, pitch: float = 0.0, heading: float = 0.0, flags: int = 0,
               stds: Sequence[float] = (0.0,) * 9, imu: Sequence[float] = (0.0,) * 12, odo_scale: float = 1.0,
               mount_pitch: float = 0.0, mount_yaw: float = 0.0) -> bytes:
    """Build a 0x04 packet (test sender, fixtures). `flags` is in C-side bit order."""
    payload = NAV.pack(round(time_s * 1e6), lat, lon, height, vn, ve, vu, roll, pitch, heading,
                       *stds, *imu, reverse_bits8(flags), odo_scale, mount_pitch, mount_yaw)
    return frame(NAV_ID, payload)


def encode_status(state: int, action: int, session: int, sequence: int, gnss_quality: int = 0,
                  uptime_ms: int = 0, health: int = 0, inhibit: int = 0, nav_flags: int = 0,
                  nav_rate_dhz: int = 0, nav_age_ms: int = NAV_AGE_UNKNOWN, msg_id: int = STATUS_ID) -> bytes:
    payload = STATUS.pack(STATUS_VERSION, state, action, gnss_quality, session, sequence, uptime_ms, health,
                          inhibit, nav_flags, 0, nav_rate_dhz, nav_age_ms, 0)
    return frame(msg_id, payload)
