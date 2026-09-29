#!/usr/bin/env python3
"""Low-dependency structural checks for metadata used by CI and maintainers."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


def main() -> int:
    root = Path(__file__).parents[1]
    config = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    required_false = ("host_network", "full_access", "hassio_api", "homeassistant_api", "docker_api")
    failed = [key for key in required_false if config.get(key) is not False]
    if config.get("ports", {}).get("4403/tcp", "missing") is not None:
        failed.append("4403/tcp must not be host-published")
    if set(config.get("ports", {})) != {"4403/tcp"}:
        failed.append("only the internal 4403/tcp Stream API may be declared")
    schema = config.get("schema")
    if not isinstance(schema, dict) or schema.get("usb_selector") != "list(serial|unique_serialless)":
        failed.append("schema must preserve the supported USB selector values")
    expected_hardware_schema = {
        "mode": "list(profile|custom|customized_profile)",
        "profile": "str",
        "auto_detect": "bool",
        "overrides_yaml": "str",
        "config": "str",
    }
    if not isinstance(schema, dict) or schema.get("hardware") != expected_hardware_schema:
        failed.append("schema must save generic hardware YAML text fields")
    if not (root / "apparmor.txt").is_file():
        failed.append("custom AppArmor profile is missing")
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    if not re.search(
        r"^FROM meshtastic/meshtasticd:[0-9][A-Za-z0-9.]+-(?:alpha|beta)-alpine@sha256:[0-9a-f]{64}$",
        dockerfile,
        flags=re.MULTILINE,
    ):
        failed.append("Dockerfile must pin an official upstream alpha/beta Alpine image by digest")
    if failed:
        print("Invalid App security metadata: " + ", ".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
