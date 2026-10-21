from __future__ import annotations

import struct

import pytest

from aio_receiver.core import protocol as P
from helpers import ALIGNED, GOLDEN, nav


def test_golden_status_vector_decodes_and_reencodes() -> None:
    s = P.decode_status(GOLDEN)
    assert s is not None
    assert (s.state, s.action, s.gnss_quality, s.session, s.sequence) == (6, 0, 3, 0x12345678, 482)
    assert (s.uptime_ms, s.health, s.inhibit, s.nav_flags, s.nav_rate_dhz, s.nav_age_ms) == (
        123456789, 0x10FFF, 0, 0xE8, 1000, 12)
    assert P.encode_status(6, 0, 0x12345678, 482, 3, 123456789, 0x10FFF, 0, 0xE8, 1000, 12) == GOLDEN


def test_nav_roundtrip_flags_and_time() -> None:
    pkt = nav(300000.5, flags=ALIGNED | 1)
    assert len(pkt) == P.NAV_LEN == 156
    n = P.decode_nav(pkt)
    assert n is not None
    assert n.flags == ALIGNED | 1
    assert n.has_flag("ZUPT") and n.has_flag("FINE") and not n.has_flag("GNSS")
    assert n.time_s == pytest.approx(300000.5)
    assert P.pack_nav(n) == pkt


def test_heading_is_sent_as_is() -> None:
    pkt = P.encode_nav(0, 0, 0, heading=-90.0)
    assert pkt[5 + 8 + 16 + 4 * 6:][:4] == struct.pack("<f", -90.0)


def test_flags_are_bit_reversed_on_the_wire() -> None:
    assert P.reverse_bits8(0b0000_0001) == 0b1000_0000
    assert all(P.reverse_bits8(P.reverse_bits8(i)) == i for i in range(256))
    pkt = P.encode_nav(0, 0, 0, flags=0b0000_0001)
    assert P.decode_nav(pkt).flags_wire == 0b1000_0000  # type: ignore[union-attr]


@pytest.mark.parametrize("mutate", [
    lambda p: p[:-1] + bytes([p[-1] ^ 1]),          # checksum
    lambda p: p[:-1],                               # length
    lambda p: b"\x55\xAB" + p[2:],                  # sync
    lambda p: p[:3] + b"\x95\x00" + p[5:],          # payload length field
])
def test_malformed_nav_is_rejected(mutate) -> None:  # type: ignore[no-untyped-def]
    assert P.decode_nav(mutate(nav(1.0))) is None


def test_status_version_and_id_are_checked() -> None:
    v2 = P.frame(P.STATUS_ID, bytes([2]) + GOLDEN[6:-1])
    assert P.decode_status(v2) is None
    assert P.decode_status(GOLDEN, msg_id=0x06) is None
    assert P.decode_status(P.encode_status(6, 0, 1, 1, msg_id=0x06), msg_id=0x06) is not None


def test_names_and_bits() -> None:
    assert P.bit_names(0b101, P.INHIBIT_BITS) == ["BOOT_IN_PROGRESS", "IMU_MISSING_OR_STALE"]
    assert P.name_of(6, P.STATES) == "READY"
    assert P.name_of(99, P.STATES) == "#99"
    assert P.message_id(b"\x55\xAA\x05") == 5 and P.message_id(b"xx") is None
