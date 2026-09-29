#!/usr/bin/env python3
"""Emit the published-image metadata needed by the Home Assistant build actions."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


FIELDS = ("name", "version", "image")


def metadata(config_path: Path) -> dict[str, str]:
    content = config_path.read_text(encoding="utf-8")
    values: dict[str, str] = {}
    for field in FIELDS:
        match = re.search(rf"^{field}:\s*(.+)$", content, flags=re.MULTILINE)
        if not match:
            raise ValueError(f"Missing {field} in {config_path}")
        values[field] = match.group(1).strip().strip('"')
    if "REPLACE_WITH_GITHUB_OWNER" in values["image"]:
        raise ValueError(
            "Replace REPLACE_WITH_GITHUB_OWNER in both App image fields with the GitHub owner before publishing"
        )
    if not values["image"].startswith("ghcr.io/"):
        raise ValueError("Published App images must use GitHub Container Registry")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    arguments = parser.parse_args()
    try:
        values = metadata(arguments.app / "config.yaml")
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")
    else:
        for key, value in values.items():
            print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
