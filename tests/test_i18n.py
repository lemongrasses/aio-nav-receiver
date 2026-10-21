"""One language at a time: the table is complete, and nothing outside it leaks into the other language."""

from __future__ import annotations

import errno
import re
import string
from pathlib import Path

import pytest

from aio_receiver import config, i18n
from aio_receiver.core import protocol as P
from aio_receiver.core.gate import Reason, Verdict
from aio_receiver.engine import _event_text

CJK = re.compile(r"[　-〿一-鿿＀-￯]")


def fields(text: str) -> set:  # type: ignore[type-arg]
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_message_exists_in_both_languages_with_the_same_fields() -> None:
    for key, (zh, en) in i18n._T.items():
        assert zh and en, key
        assert fields(zh) == fields(en), key
        assert not CJK.search(en), f"Chinese in the English text of {key}"


def test_protocol_vocabulary_is_complete() -> None:
    assert set(i18n._STATES) == set(P.STATES)
    assert set(i18n._ACTIONS) == set(P.ACTIONS)
    assert len(i18n._HEALTH) == len(P.HEALTH_BITS) and len(i18n._INHIBIT) == len(P.INHIBIT_BITS)
    for pairs in (i18n._STATES.values(), i18n._ACTIONS.values(), i18n._HEALTH, i18n._INHIBIT, i18n._GNSS_QUALITY):
        for zh, en in pairs:
            assert zh and en and not CJK.search(en)


def test_switching_language() -> None:
    v = Verdict(False, Reason.NOT_READY, P.STATES.index("MOVE_STRAIGHT"), 1 << 8 | 1 << 9)
    assert v.word == "阻擋" and v.text == "狀態不是就緒：直線行駛（需要直線行駛、需要精對準）"
    assert i18n.set_language("en") == "en"
    assert v.word == "Blocked"
    assert v.text == "Status is not ready: Drive straight (Must drive straight, Fine alignment needed)"
    assert _event_text(v) == ("Blocked Status is not ready: Drive straight (Must drive straight, Fine alignment "
                              "needed) [not_ready]")
    assert i18n.set_language("") in i18n.LANGUAGES                     # "" follows the system
    assert i18n.system_language() in i18n.LANGUAGES


def test_messages_render_when_shown_not_when_made() -> None:
    m = i18n.msg("fail.bind", addr="0.0.0.0:9000", error=i18n.os_error(OSError(errno.EADDRINUSE, "x")))
    assert str(m) == "無法監聽 0.0.0.0:9000：這個埠已被其他程式使用"
    i18n.set_language("en")
    assert str(m) == "Cannot listen on 0.0.0.0:9000: the port is in use by another program"
    assert str(i18n.os_error(OSError(errno.ENOSPC, "x"))) == "the disk is full"
    rare = i18n.os_error(OSError(errno.ECHILD, "原文"))
    assert str(rare).startswith("system error ")


def test_settings_validation_speaks_the_current_language(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="埠號要在 1–65535"):
        config.parse_field("nav_port", "70000")
    i18n.set_language("en")
    with pytest.raises(ValueError, match="The port must be 1–65535"):
        config.parse_field("nav_port", "70000")
    with pytest.raises(ValueError, match="not a number"):
        config.parse_field("nav_port", "abc")
    assert config.parse_field("language", "en") == "en" and config.parse_field("language", "") == ""
    with pytest.raises(ValueError):
        config.parse_field("language", "fr")
    f = tmp_path / "s.json"
    config.save(config.Settings(language="en"), f)
    assert config.load(f)[0].language == "en"


def test_command_line_output_in_english(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    from aio_receiver import cli
    from helpers import fixture_file

    path = fixture_file("real_ready_v2.bin.gz", tmp_path)
    i18n.set_language("en")
    cli._check(path, False, config.Settings())
    out = capsys.readouterr().out
    assert "usable 10.9 s" in out and "Confirming" not in out and not CJK.search(out)
