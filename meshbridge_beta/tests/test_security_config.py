from __future__ import annotations

import re
from pathlib import Path

import yaml


def test_no_host_network_or_privileged_api_or_lan_ports() -> None:
    config = yaml.safe_load((Path(__file__).parents[1] / "config.yaml").read_text())
    assert config["host_network"] is False
    assert config["full_access"] is False
    assert config["usb"] is True
    assert config["apparmor"] is True
    assert config["hassio_api"] is False
    assert config["homeassistant_api"] is False
    assert config["docker_api"] is False
    assert config["privileged"] == []
    assert config["ports"]["4403/tcp"] is None
    assert set(config["ports"]) == {"4403/tcp"}
    assert config["stage"] == "experimental"
    assert config["schema"]["usb_selector"] == "list(serial|unique_serialless)"
    assert config["schema"]["hardware"] == {
        "mode": "list(profile|custom|customized_profile)",
        "profile": "str",
        "auto_detect": "bool",
        "overrides_yaml": "str",
        "config": "str",
    }


def test_official_upstream_image_is_pinned_directly_in_dockerfile() -> None:
    dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()
    assert re.search(
        r"^FROM meshtastic/meshtasticd:[0-9][A-Za-z0-9.]+-(?:alpha|beta)-alpine@sha256:[0-9a-f]{64}$",
        dockerfile,
        flags=re.MULTILINE,
    )
    assert "PYTHONSAFEPATH=1" in dockerfile
    assert "PYTHONDONTWRITEBYTECODE=1" in dockerfile


def test_apparmor_is_custom_and_has_no_global_write_rule() -> None:
    root = Path(__file__).parents[1]
    profile = (root / "apparmor.txt").read_text()
    slug = yaml.safe_load((root / "config.yaml").read_text())["slug"]
    assert f"profile {slug} " in profile
    assert "/run.sh rix," in profile
    assert "/usr/bin/python3* rix," in profile
    assert "/usr/local/bin/ r," in profile
    assert "/usr/local/bin/meshbridge-listener-ready rix," in profile
    assert "/usr/local/lib/ r," in profile
    assert "/usr/local/lib/meshbridge_app/ r," in profile
    assert "/proc/*/net/tcp r," in profile
    assert "/proc/*/net/tcp6 r," in profile
    assert "/proc/*/mounts r," in profile
    assert "/proc/version_signature r," in profile
    assert "/etc/meshbridge-release r," in profile
    assert "/lib/ r," in profile
    assert "/usr/lib/ r," in profile
    assert "/data/ r," in profile
    assert "/dev/ r," in profile
    assert "/dev/bus/usb/** rw," in profile
    assert "/dev/bus/usb/ r," in profile
    assert "/sys/bus/usb/devices/ r," in profile
    assert "/sys/bus/usb/devices/** r," in profile
    assert "/sys/devices/**/busnum r," in profile
    assert "/sys/devices/**/devnum r," in profile
    assert "/sys/devices/**/speed r," in profile
    assert "/sys/devices/**/descriptors r," in profile
    assert "network netlink raw," in profile
    assert "deny network bluetooth raw," in profile
    assert "network bluetooth raw," not in profile.replace("deny network bluetooth raw,", "")
    assert re.search(r"^\s*/\*\* rw,", profile, flags=re.MULTILINE) is None
