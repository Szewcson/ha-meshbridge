#!/usr/bin/env python3
"""Ensure the release-channel Apps use the same audited wrapper implementation."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


SHARED_FILES = (
    "run.sh",
    "requirements-dev.txt",
    "scripts/validate_app.py",
    "rootfs/usr/local/bin/meshbridge-listener-ready",
    "rootfs/usr/local/lib/meshbridge_app/__init__.py",
    "rootfs/usr/local/lib/meshbridge_app/app_state.py",
    "rootfs/usr/local/lib/meshbridge_app/hardware.py",
    "rootfs/usr/local/lib/meshbridge_app/launcher.py",
    "rootfs/usr/local/lib/meshbridge_app/usb.py",
    "tests/conftest.py",
    "tests/test_app_state.py",
    "tests/test_hardware.py",
    "tests/test_security_config.py",
    "tests/test_usb.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    beta = repository / "meshbridge_beta"
    alpha = repository / "meshbridge_alpha"
    failed: list[str] = []

    for relative_path in SHARED_FILES:
        beta_path = beta / relative_path
        alpha_path = alpha / relative_path
        if not beta_path.is_file() or not alpha_path.is_file():
            failed.append(f"missing shared file: {relative_path}")
        elif digest(beta_path) != digest(alpha_path):
            failed.append(f"channel wrapper drift: {relative_path}")

    if failed:
        print("\n".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
