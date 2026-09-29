#!/usr/bin/env python3
"""Render human-readable MeshBridge release provenance from upstream.yaml."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_FILE = ROOT / "upstream.yaml"
CHANNELS = ("beta", "alpha")


def load_metadata(content: str) -> dict[str, Any]:
    loaded = yaml.safe_load(content)
    if not isinstance(loaded, dict) or not isinstance(loaded.get("channels"), dict):
        raise ValueError("upstream.yaml must contain a channels mapping")
    return loaded


def changed_channels(current: dict[str, Any]) -> tuple[str, ...]:
    """Return channels whose canonical provenance differs from HEAD."""

    try:
        previous = subprocess.run(
            ["git", "show", "HEAD:upstream.yaml"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return CHANNELS
    try:
        old_channels = load_metadata(previous.stdout)["channels"]
    except (ValueError, yaml.YAMLError):
        return CHANNELS
    current_channels = current["channels"]
    return tuple(
        channel
        for channel in CHANNELS
        if current_channels.get(channel) != old_channels.get(channel)
    )


def render(channel: str, metadata: dict[str, Any]) -> str:
    required = ("app_version", "version", "digest", "source_tag", "source_url")
    if any(not isinstance(metadata.get(field), str) or not metadata[field] for field in required):
        raise ValueError(f"upstream.yaml {channel} is incomplete")
    return "\n".join(
        (
            f"## MeshBridge {channel.title()} {metadata['app_version']}",
            "",
            "Upstream meshtasticd",
            f"Channel: {channel.title()}",
            f"Version: {metadata['version']}",
            f"OCI digest: {metadata['digest']}",
            f"Upstream release/tag: {metadata['source_tag']}",
            f"Upstream source: {metadata['source_url']}",
            "",
            "MeshBridge version:",
            metadata["app_version"],
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Render only channels whose canonical metadata differs from HEAD.",
    )
    arguments = parser.parse_args()
    try:
        metadata = load_metadata(UPSTREAM_FILE.read_text(encoding="utf-8"))
        selected = changed_channels(metadata) if arguments.changed_only else CHANNELS
        if not selected:
            return 0
        print("\n\n".join(render(channel, metadata["channels"][channel]) for channel in selected))
    except (OSError, ValueError, yaml.YAMLError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
