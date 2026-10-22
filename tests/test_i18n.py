"""One language at a time: the table is complete, nothing outside it leaks into the other language, and the
Chinese follows docs/TERMINOLOGY.zh-TW.md (shared with web_monitor) on the desktop, Android and iOS alike."""

from __future__ import annotations

import errno
import json
import re
import string
from pathlib import Path

import pytest

from aio_receiver import config, i18n
from aio_receiver.core import protocol as P
from aio_receiver.core.gate import Reason, Verdict
from aio_receiver.engine import _event_text

CJK = re.compile(r"[　-〿一-鿿＀-￯]")
ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = (ROOT / "docs/TERMINOLOGY.zh-TW.md").read_text(encoding="utf-8")   # the same file in web_monitor


def glossary(heading: str) -> list:  # type: ignore[type-arg]
    """The rows (lists of cells) of the table under `heading` in docs/TERMINOLOGY.zh-TW.md."""
    rows = []
    for line in GLOSSARY.split(f"\n{heading}\n", 1)[1].splitlines():
        if line.startswith("|"):
            rows.append([cell.strip().strip("`") for cell in line.strip().strip("|").split("|")])
        elif rows:
            break
    return rows[2:]                                     # without the header and the |---| line


def avoided(texts: list) -> list:  # type: ignore[type-arg]
    """The glossary's 不使用的詞 found in `texts`, except as part of the word to use (時間戳 in 時間戳記)."""
    found = set()
    for avoid, use, _why in glossary("## 不使用的詞"):
        keep = [(w, w.index(avoid)) for w in use.split("、") if avoid in w]
        for text in texts:
            for m in re.finditer(re.escape(avoid), text):
                if not any(m.start() >= i and text.startswith(w, m.start() - i) for w, i in keep):
                    found.add(f"{avoid} -> {use}: {text}")
    return sorted(found)


def fields(text: str) -> set:  # type: ignore[type-arg]
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_message_exists_in_both_languages_with_the_same_fields() -> None:
    for key, (zh, en) in i18n._T.items():
        assert zh and en, key
        assert fields(zh) == fields(en), key
        assert not CJK.search(en), f"Chinese in the English text of {key}"


def test_chinese_follows_the_shared_terminology() -> None:
    zh = [pair[0] for pair in i18n._T.values()] + [pair[0] for pair in i18n._STATES.values()]
    zh += [pair[0] for table in (i18n._ACTIONS.values(), i18n._LAMPS.values()) for pair in table]
    zh += [pair[0] for table in (i18n._GNSS_QUALITY, i18n._HEALTH, i18n._INHIBIT) for pair in table]
    zh += re.findall(r"<(?:string|item)\b[^>]*>([^<]*)<", (ROOT / "android/app/src/main/res/values-zh-rTW/strings.xml")
                     .read_text(encoding="utf-8"))
    catalog = json.loads((ROOT / "ios/MyApp/Localizable.xcstrings").read_text(encoding="utf-8"))
    zh += [e["localizations"]["zh-Hant"]["stringUnit"]["value"] for e in catalog["strings"].values()]
    zh += re.findall(r'\(\s*"([^"]*)"\s*,', (ROOT / "ios/MyApp/Protocol/Vocabulary.swift").read_text(encoding="utf-8"))
    assert len(zh) > 400
    assert avoided(zh) == []


def test_protocol_vocabulary_is_the_shared_glossary() -> None:
    """i18n.py, and through it the iPhone and Android tables, says what docs/TERMINOLOGY.zh-TW.md says."""
    states = glossary("### 狀態（state）")
    assert [r[1] for r in states] == list(P.STATES)
    assert {r[1]: (r[2], r[3]) for r in states} == i18n._STATES
    actions = glossary("### 要求的動作（requested_action）")
    assert [r[1] for r in actions] == list(P.ACTIONS)
    assert {r[1]: (r[2], r[4]) for r in actions} == i18n._ACTIONS
    assert [(r[1], r[2]) for r in glossary("### GNSS 品質（gnss_quality）")] == list(i18n._GNSS_QUALITY)
    for heading, names, table in (("### 成立條件（health_flags）", P.HEALTH_BITS, i18n._HEALTH),
                                  ("### 不可用原因（inhibit_flags）", P.INHIBIT_BITS, i18n._INHIBIT)):
        rows = glossary(heading)
        assert [r[1] for r in rows] == list(names), heading
        assert [(r[2], r[3]) for r in rows] == list(table), heading
    assert {r[0]: (r[1], r[2]) for r in glossary("### 對準旗標（0x04 flags）")} == i18n._LAMPS


def test_protocol_vocabulary_is_complete() -> None:
    assert set(i18n._STATES) == set(P.STATES)
    assert set(i18n._ACTIONS) == set(P.ACTIONS)
    assert len(i18n._HEALTH) == len(P.HEALTH_BITS) and len(i18n._INHIBIT) == len(P.INHIBIT_BITS)
    for pairs in (i18n._STATES.values(), i18n._ACTIONS.values(), i18n._HEALTH, i18n._INHIBIT, i18n._GNSS_QUALITY):
        for zh, en in pairs:
            assert zh and en and not CJK.search(en)


def test_switching_language() -> None:
    v = Verdict(False, Reason.NOT_READY, P.STATES.index("MOVE_STRAIGHT"), 1 << 8 | 1 << 9)
    assert v.word == "不可用" and v.text == "狀態不是就緒：直線行駛（需要直線行駛、需要精對準）"
    assert i18n.set_language("en") == "en"
    assert v.word == "Blocked"
    assert v.text == "Status is not ready: Drive straight (Must drive straight, Fine alignment needed)"
    assert _event_text(v) == ("Blocked Status is not ready: Drive straight (Must drive straight, Fine alignment "
                              "needed) [not_ready]")
    assert i18n.set_language("") in i18n.LANGUAGES                     # "" follows the system
    assert i18n.system_language() in i18n.LANGUAGES


def test_messages_render_when_shown_not_when_made() -> None:
    m = i18n.msg("fail.bind", addr="0.0.0.0:9000", error=i18n.os_error(OSError(errno.EADDRINUSE, "x")))
    assert str(m) == "無法監聽 0.0.0.0:9000：這個連接埠已被其他程式使用"
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
