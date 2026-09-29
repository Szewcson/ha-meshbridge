from __future__ import annotations

import pytest

from meshbridge_app.hardware import ConfigurationError
from meshbridge_app.usb import select_usb_device


class FakeDevice:
    def __init__(self, serial: str | None, bus: int = 1, address: int = 2) -> None:
        self.serial_number = serial
        self.bus = bus
        self.address = address


def _resolved(serial: str | None = "MT123") -> dict[str, object]:
    lora: dict[str, object] = {"USB_VID": 0x1A86, "USB_PID": 0x5512}
    if serial is not None:
        lora["USB_Serialnum"] = serial
    return {"Lora": lora}


def _finder(devices: list[FakeDevice]):
    def find(vendor_id: int, product_id: int) -> list[FakeDevice]:
        assert (vendor_id, product_id) == (0x1A86, 0x5512)
        return devices

    return find


def test_exact_configured_serial_selects_only_one_match() -> None:
    device = select_usb_device(_resolved(), "serial", "MT123", _finder([FakeDevice("MT123")]))
    assert device.serial == "MT123"


@pytest.mark.parametrize("devices", [[], [FakeDevice("OTHER")], [FakeDevice("MT123"), FakeDevice("MT123", address=3)]])
def test_missing_or_duplicate_configured_serial_fails(devices: list[FakeDevice]) -> None:
    with pytest.raises(ConfigurationError, match="exactly one"):
        select_usb_device(_resolved(), "serial", "MT123", _finder(devices))


def test_serial_profile_must_bind_to_preflight_serial() -> None:
    with pytest.raises(ConfigurationError, match="USB_Serialnum"):
        select_usb_device(_resolved("OTHER"), "serial", "MT123", _finder([FakeDevice("MT123")]))


def test_serialless_device_is_not_selected_in_serial_mode() -> None:
    with pytest.raises(ConfigurationError, match="exactly one"):
        select_usb_device(_resolved(), "serial", "MT123", _finder([FakeDevice(None)]))


def test_unique_serialless_selects_exactly_one_total_match() -> None:
    device = select_usb_device(_resolved(None), "unique_serialless", "", _finder([FakeDevice(None)]))
    assert device.serial is None


@pytest.mark.parametrize("devices", [[], [FakeDevice(None), FakeDevice(None, address=3)], [FakeDevice(None), FakeDevice("MT123")]])
def test_ambiguous_serialless_selection_fails(devices: list[FakeDevice]) -> None:
    with pytest.raises(ConfigurationError, match="exactly one total"):
        select_usb_device(_resolved(None), "unique_serialless", "", _finder(devices))
