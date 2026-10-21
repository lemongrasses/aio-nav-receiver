from __future__ import annotations

import json
from pathlib import Path

import pytest

from aio_receiver import config
from aio_receiver.config import Settings


def test_defaults_and_old_file_format(tmp_path: Path) -> None:
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"host": "0.0.0.0", "nav_port": 9000, "status_port": 0, "status_id": "0x05",
                             "allowed_from": "", "status_timeout": 3.0, "ready_stable": 2.0, "nav_max_age": 0.5}))
    s, problems = config.load(f)
    assert (s, problems) == (Settings(), [])
    assert config.load(tmp_path / "missing.json") == (Settings(), [])


def test_bad_fields_fall_back_one_by_one(tmp_path: Path) -> None:
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"nav_port": 70000, "host": "nope", "status_timeout": "2.5", "status_id": 6}))
    s, problems = config.load(f)
    assert s.nav_port == 9000 and s.host == "0.0.0.0"
    assert s.status_timeout == 2.5 and s.status_id == 6
    assert len(problems) == 2
    f.write_text("{not json")
    assert config.load(f)[0] == Settings()


def test_save_load_roundtrip(tmp_path: Path) -> None:
    f = tmp_path / "s.json"
    s = Settings(nav_port=9100, status_port=9101, allowed_from="192.168.116.1", record_csv=False,
                 record_dir="E:/logs")
    config.save(s, f)
    assert config.load(f) == (s, [])
    assert json.loads(f.read_text())["status_id"] == "0x05"
    assert s.ports == [9100, 9101] and Settings().ports == [9000]
    assert s.gate_config().allowed_from == "192.168.116.1"
    assert s.gate_config(use_source_filter=False).allowed_from is None


@pytest.mark.parametrize("name,value", [
    ("nav_port", "0"), ("status_port", "-1"), ("status_id", "0x04"), ("status_id", "300"),
    ("allowed_from", "192.168.1"), ("status_timeout", "0"), ("nav_max_age", "61"), ("record_csv", "maybe")])
def test_invalid_values(name: str, value: str) -> None:
    with pytest.raises(ValueError):
        config.parse_field(name, value)


def test_valid_values() -> None:
    assert config.parse_field("status_id", "0x06") == 6
    assert config.parse_field("ready_stable", "0") == 0.0
    assert config.parse_field("allowed_from", " ") == ""
    assert config.parse_field("record_csv", "false") is False
