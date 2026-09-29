"""Fail-closed USB matching for the active meshtasticd configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from .hardware import ConfigurationError


@dataclass(frozen=True)
class SelectedUSBDevice:
    vendor_id: int
    product_id: int
    serial: str | None
    bus: int | None
    address: int | None


def _usb_id(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ConfigurationError(f"Lora.{field} must be a USB integer")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str):
        try:
            result = int(value, 0)
        except ValueError as error:
            raise ConfigurationError(f"Lora.{field} is not a valid integer") from error
    else:
        raise ConfigurationError(f"Lora.{field} is required for USB selector validation")
    if not 0 <= result <= 0xFFFF:
        raise ConfigurationError(f"Lora.{field} must fit in an unsigned 16-bit USB ID")
    return result


def _lora_usb_ids(resolved: Mapping[str, Any]) -> tuple[int, int, Mapping[str, Any]]:
    lora = resolved.get("Lora")
    if not isinstance(lora, dict):
        raise ConfigurationError("active hardware configuration needs a Lora mapping for USB selection")
    return _usb_id(lora.get("USB_VID"), "USB_VID"), _usb_id(lora.get("USB_PID"), "USB_PID"), lora


def select_usb_device(
    resolved: Mapping[str, Any],
    selector: str,
    configured_serial: str,
    find_devices: Callable[[int, int], Iterable[Any]],
) -> SelectedUSBDevice:
    """Select a device only when the runtime config binds to the same device.

    `USB_Serialnum` is the upstream meshtasticd CH341 field. Serial mode
    requires it to match exactly; this prevents preflight from validating one
    device while meshtasticd later opens an arbitrary VID/PID match.
    """

    vendor_id, product_id, lora = _lora_usb_ids(resolved)
    matches: list[SelectedUSBDevice] = []
    for device in find_devices(vendor_id, product_id):
        try:
            serial = device.serial_number
        except Exception as error:  # libusb permission/descriptor failure
            raise ConfigurationError(f"cannot read USB serial descriptor: {error}") from error
        matches.append(
            SelectedUSBDevice(
                vendor_id=vendor_id,
                product_id=product_id,
                serial=serial if serial not in (None, "") else None,
                bus=getattr(device, "bus", None),
                address=getattr(device, "address", None),
            )
        )

    if selector == "serial":
        if not isinstance(configured_serial, str) or not configured_serial:
            raise ConfigurationError("usb_serial is required when usb_selector is serial")
        native_serial = lora.get("USB_Serialnum")
        if not isinstance(native_serial, str) or native_serial != configured_serial:
            raise ConfigurationError(
                "serial selection requires Lora.USB_Serialnum to be the exact usb_serial value; "
                "use customized_profile to add it without changing the upstream stock profile"
            )
        selected = [device for device in matches if device.serial == configured_serial]
        if len(selected) != 1:
            raise ConfigurationError(
                f"expected exactly one USB device with serial {configured_serial!r}; found {len(selected)}"
            )
        return selected[0]

    if selector == "unique_serialless":
        if lora.get("USB_Serialnum") not in (None, ""):
            raise ConfigurationError("unique_serialless requires a profile without Lora.USB_Serialnum")
        serialless = [device for device in matches if device.serial is None]
        # The upstream no-serial path is VID/PID based. A serial-bearing peer
        # would make its runtime choice ambiguous, so fail instead of relying
        # on enumeration order.
        if len(matches) != 1 or len(serialless) != 1:
            raise ConfigurationError(
                "unique_serialless requires exactly one total matching USB device and it must have no serial descriptor"
            )
        return serialless[0]

    raise ConfigurationError("usb_selector must be serial or unique_serialless")


def pyusb_devices(vendor_id: int, product_id: int) -> Iterable[Any]:
    try:
        import usb.core
    except ImportError as error:
        raise ConfigurationError("PyUSB is unavailable in this App image") from error
    try:
        devices = usb.core.find(find_all=True, idVendor=vendor_id, idProduct=product_id)
        return list(devices or [])
    except Exception as error:
        raise ConfigurationError(f"USB enumeration failed: {error}") from error
