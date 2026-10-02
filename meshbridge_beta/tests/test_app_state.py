from __future__ import annotations

import json
import re

import pytest

from meshbridge_app.app_state import SCHEMA_VERSION, StateError, ensure_current, startup_lock


def test_new_state_is_created_atomically(tmp_path) -> None:
    state = ensure_current(tmp_path)
    assert state["schema_version"] == SCHEMA_VERSION
    assert re.fullmatch(r"[0-9A-F]{12}", state["mac_address"])
    assert int(state["mac_address"][:2], 16) & 0x03 == 0x02
    assert json.loads((tmp_path / "app-state.json").read_text()) == state
    assert not list(tmp_path.glob(".app-state.json.*.new"))


def test_schema_one_state_gets_a_persistent_mac_migration(tmp_path) -> None:
    path = tmp_path / "app-state.json"
    path.write_text('{"schema_version":1}\n')
    migrated = ensure_current(tmp_path)
    assert migrated["schema_version"] == SCHEMA_VERSION
    assert re.fullmatch(r"[0-9A-F]{12}", migrated["mac_address"])
    assert ensure_current(tmp_path) == migrated


def test_current_state_rejects_an_invalid_mac_address(tmp_path) -> None:
    (tmp_path / "app-state.json").write_text('{"schema_version":2,"mac_address":"invalid"}\n')
    with pytest.raises(StateError, match="valid generated mac_address"):
        ensure_current(tmp_path)


def test_newer_state_refuses_downgrade(tmp_path) -> None:
    (tmp_path / "app-state.json").write_text('{"schema_version": 999}\n')
    with pytest.raises(StateError, match="refusing downgrade"):
        ensure_current(tmp_path)


def test_boolean_schema_version_is_not_an_integer_schema(tmp_path) -> None:
    (tmp_path / "app-state.json").write_text('{"schema_version":true}\n')
    with pytest.raises(StateError, match="schema_version integer"):
        ensure_current(tmp_path)


def test_unregistered_older_state_fails_without_rewrite(tmp_path) -> None:
    path = tmp_path / "app-state.json"
    original = '{"schema_version": 0}\n'
    path.write_text(original)
    with pytest.raises(StateError, match="no migration"):
        ensure_current(tmp_path)
    assert path.read_text() == original


def test_startup_lock_rejects_a_symlink(tmp_path) -> None:
    (tmp_path / ".meshbridge-start.lock").symlink_to(tmp_path / "other")
    with pytest.raises(StateError, match="cannot acquire startup lock"):
        with startup_lock(tmp_path):
            pass
