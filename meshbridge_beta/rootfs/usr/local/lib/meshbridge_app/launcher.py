#!/usr/bin/env python3
"""Validate state, derive hardware configuration, and prove USB selection."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from meshbridge_app.app_state import StateError, ensure_current
from meshbridge_app.hardware import ConfigurationError, generate_configuration, load_options
from meshbridge_app.usb import pyusb_devices, select_usb_device


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--options", required=True, type=Path)
    parser.add_argument("--available-dir", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    return parser.parse_args()


def _configure_logging(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ConfigurationError("log_level must be trace, debug, info, warning, or error")
    logging.basicConfig(level=numeric_level, format="%(levelname)s: %(message)s")


def main() -> int:
    arguments = _arguments()
    try:
        options = load_options(arguments.options)
        level = options.get("log_level", "info")
        _configure_logging("debug" if level == "trace" else level)
        release = Path("/etc/meshbridge-release")
        if release.exists():
            for line in release.read_text(encoding="utf-8").splitlines():
                if line.startswith(("app_version=", "upstream_version=")):
                    logging.info("%s", line.replace("=", ": ", 1))
        state = ensure_current(arguments.data_dir)
        generated = generate_configuration(
            options,
            arguments.available_dir,
            arguments.data_dir,
            state["mac_address"],
        )
        device = select_usb_device(
            generated.prepared.resolved,
            options.get("usb_selector"),
            options.get("usb_serial", ""),
            pyusb_devices,
        )
    except (ConfigurationError, StateError) as error:
        logging.error("Startup validation failed: %s", error)
        return 1

    logging.info("Hardware configuration mode: %s", generated.prepared.mode)
    if generated.prepared.profile_name:
        logging.info("Base profile: %s", generated.prepared.profile_name)
    if generated.prepared.auto_detect:
        logging.info("Hardware auto-detection: enabled (generated available.d overlay)")
    logging.info("Generated profile: %s", generated.hardware_config)
    for path in generated.prepared.override_paths:
        logging.info("Applied override: %s", path)
    serial_description = device.serial if device.serial is not None else "serial absent"
    logging.info(
        "Selected USB device: %04x:%04x serial=%s bus=%s address=%s",
        device.vendor_id,
        device.product_id,
        serial_description,
        device.bus,
        device.address,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
