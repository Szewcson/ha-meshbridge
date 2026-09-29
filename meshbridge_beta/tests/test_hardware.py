from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from meshbridge_app.hardware import ConfigurationError, deep_merge, generate_configuration, prepare_hardware


def _installed_files(tmp_path: Path) -> Path:
    available = tmp_path / "installed" / "available.d"
    available.mkdir(parents=True)
    (available / "lora-usb-test.yaml").write_text(
        "Meta:\n  name: upstream\nLora:\n  Module: sx1262\n  USB_VID: 0x1a86\n  USB_PID: 0x5512\n  pins: [1, 2]\n",
        encoding="utf-8",
    )
    return available


def _options(hardware: dict[str, object]) -> dict[str, object]:
    return {"hardware": hardware, "usb_selector": "serial", "usb_serial": "0013374201"}


def test_deep_merge_keeps_upstream_values_and_replaces_lists() -> None:
    merged = deep_merge(
        {"Lora": {"Module": "sx1262", "Nested": {"keep": 1, "change": 2}, "pins": [1, 2]}},
        {"Lora": {"Nested": {"change": 3}, "pins": [9]}},
    )
    assert merged == {"Lora": {"Module": "sx1262", "Nested": {"keep": 1, "change": 3}, "pins": [9]}}


def test_customized_profile_generates_complete_resolved_profile(tmp_path: Path) -> None:
    available = _installed_files(tmp_path)
    generated = generate_configuration(
        _options(
            {
                "mode": "customized_profile",
                "profile": "lora-usb-test",
                "config": "",
                "overrides": {"Lora": {"USB_PID": 0x1234, "USB_Serialnum": "0013374201"}},
            }
        ),
        available,
        tmp_path / "data",
        "021122334455",
    )
    resolved = yaml.safe_load(generated.hardware_config.read_text(encoding="utf-8"))
    assert resolved["Meta"]["name"] == "upstream"
    assert resolved["Lora"]["Module"] == "sx1262"
    assert resolved["Lora"]["USB_PID"] == 0x1234
    assert resolved["Lora"]["USB_Serialnum"] == "0013374201"
    runtime = yaml.safe_load(generated.runtime_config.read_text(encoding="utf-8"))
    assert runtime["General"]["MACAddress"] == "021122334455"
    assert runtime["General"]["TCPPort"] == 4403
    assert "Webserver" not in runtime
    assert (generated.current_directory / "active.d" / "10-hardware.yaml").resolve() == generated.hardware_config.resolve()
    assert (generated.current_directory / "available.d" / "lora-usb-test.yaml").resolve() == generated.hardware_config.resolve()


def test_customized_profile_parses_ui_override_yaml(tmp_path: Path) -> None:
    available = _installed_files(tmp_path)
    generated = generate_configuration(
        _options(
            {
                "mode": "customized_profile",
                "profile": "lora-usb-test",
                "config": "",
                "overrides_yaml": "Lora:\n  USB_PID: 0x1234\n  USB_Serialnum: '0013374201'\n",
            }
        ),
        available,
        tmp_path / "data",
        "021122334455",
    )
    resolved = yaml.safe_load(generated.hardware_config.read_text(encoding="utf-8"))
    assert resolved["Lora"]["USB_PID"] == 0x1234
    assert resolved["Lora"]["USB_Serialnum"] == "0013374201"


def test_stock_profile_is_referenced_instead_of_copied(tmp_path: Path) -> None:
    available = _installed_files(tmp_path)
    generated = generate_configuration(
        _options({"mode": "profile", "profile": "lora-usb-test", "config": "", "overrides": {}}),
        available,
        tmp_path / "data",
        "021122334455",
    )
    assert generated.hardware_config.is_symlink()
    assert generated.hardware_config.resolve() == (available / "lora-usb-test.yaml").resolve()


def test_custom_yaml_preserves_quoted_identifier_as_string(tmp_path: Path) -> None:
    available = _installed_files(tmp_path)
    generated = generate_configuration(
        _options(
            {
                "mode": "custom",
                "profile": "",
                "overrides": {},
                "config": "Lora:\n  Module: sx1262\n  USB_VID: 0x1a86\n  USB_PID: 0x1234\n  USB_Serialnum: '0013374201'\n",
            }
        ),
        available,
        tmp_path / "data",
        "021122334455",
    )
    parsed = yaml.safe_load(generated.hardware_config.read_text(encoding="utf-8"))
    assert parsed["Lora"]["USB_Serialnum"] == "0013374201"
    assert isinstance(parsed["Lora"]["USB_Serialnum"], str)


def test_customized_profile_can_use_generated_available_tree_for_auto_detection(tmp_path: Path) -> None:
    available = _installed_files(tmp_path)
    generated = generate_configuration(
        _options(
            {
                "mode": "customized_profile",
                "profile": "lora-usb-test",
                "auto_detect": True,
                "config": "",
                "overrides": {"Lora": {"USB_PID": 0x1234, "USB_Serialnum": "0013374201"}},
            }
        ),
        available,
        tmp_path / "data",
        "021122334455",
    )
    locator = yaml.safe_load((generated.current_directory / "active.d" / "10-hardware.yaml").read_text())
    resolved = yaml.safe_load((generated.current_directory / "available.d" / "lora-usb-test.yaml").read_text())
    assert locator == {"Lora": {"Module": "auto", "USB_VID": 0x1A86, "USB_PID": 0x1234, "USB_Serialnum": "0013374201"}}
    assert resolved["Meta"]["name"] == "upstream"
    assert resolved["Lora"]["Module"] == "sx1262"


@pytest.mark.parametrize("profile", ["../../etc/passwd", "/etc/passwd", "lora-usb-test.yaml"])
def test_profile_must_be_discovered_logical_name(tmp_path: Path, profile: str) -> None:
    available = _installed_files(tmp_path)
    with pytest.raises(ConfigurationError):
        prepare_hardware(
            _options({"mode": "profile", "profile": profile, "config": "", "overrides": {}}),
            available,
        )


def test_invalid_custom_yaml_fails_before_generation(tmp_path: Path) -> None:
    available = _installed_files(tmp_path)
    with pytest.raises(ConfigurationError, match="cannot parse"):
        prepare_hardware(
            _options({"mode": "custom", "profile": "", "overrides": {}, "config": "Lora: ["}),
            available,
        )
