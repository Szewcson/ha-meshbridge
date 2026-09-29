"""Small, explicit app-state migration framework.

The hardware files under /data/generated are derived on every boot and are not
state. This file is intentionally separate from the upstream daemon's VFS state.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import uuid
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
_MAC_ADDRESS = re.compile(r"^[0-9A-F]{12}$")


class StateError(RuntimeError):
    """The persistent App state cannot safely be used."""


def _new_mac_address() -> str:
    """Return a locally administered, unicast 48-bit node identity."""

    value = bytearray(secrets.token_bytes(6))
    value[0] = (value[0] & 0xFE) | 0x02
    return value.hex().upper()


def _valid_mac_address(value: Any) -> bool:
    return isinstance(value, str) and _MAC_ADDRESS.fullmatch(value) is not None


def _fsync_directory(path: Path) -> None:
    """Make a preceding rename durable before reporting startup success."""

    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # A unique O_EXCL temporary prevents concurrent starts from truncating one
    # another's uncommitted state.  The replace remains the single visible
    # state transition.
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.new")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, sort_keys=True, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        # os.replace removes the temporary path on success.  This cleanup only
        # handles an exception before replacement and never touches state.
        if temporary.exists():
            temporary.unlink()


def _read_state(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StateError(f"cannot read {path}: {error}") from error
    if (
        not isinstance(loaded, dict)
        or not isinstance(loaded.get("schema_version"), int)
        or isinstance(loaded.get("schema_version"), bool)
    ):
        raise StateError(f"{path} does not contain a schema_version integer")
    return loaded


def ensure_current(data_dir: Path) -> dict[str, Any]:
    """Validate state and perform sequential, fail-closed migrations.

    Version 2 introduces the App-owned MAC identity, migrating version 1
    without changing daemon-owned data. Future migrations must make a
    backup before modifying that data, then register a single idempotent N ->
    N+1 function here. A newer state version is never opened by an older App
    image.
    """

    state_path = data_dir / "app-state.json"
    if not state_path.exists():
        state = {"schema_version": SCHEMA_VERSION, "mac_address": _new_mac_address()}
        _atomic_json(state_path, state)
        return state

    state = _read_state(state_path)
    version = state["schema_version"]
    if version > SCHEMA_VERSION:
        raise StateError(
            f"state schema {version} is newer than supported schema {SCHEMA_VERSION}; refusing downgrade"
        )
    if version == 1:
        migrated = dict(state)
        mac_address = migrated.get("mac_address")
        migrated["mac_address"] = mac_address if _valid_mac_address(mac_address) else _new_mac_address()
        migrated["schema_version"] = SCHEMA_VERSION
        _atomic_json(state_path, migrated)
        return migrated
    if version != SCHEMA_VERSION:
        raise StateError(
            f"no migration is registered from state schema {version} to {SCHEMA_VERSION}; refusing startup"
        )
    if not _valid_mac_address(state.get("mac_address")):
        raise StateError(f"{state_path} does not contain a valid generated mac_address")
    return state
