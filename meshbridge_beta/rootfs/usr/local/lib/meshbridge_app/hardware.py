"""Safe generation of the active meshtasticd hardware configuration."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml


class ConfigurationError(ValueError):
    """An App option or installed profile is unsafe or invalid."""


_YAML_SUFFIXES = {".yaml", ".yml"}
_SECRET_COMPONENT = re.compile(r"(?:key|secret|password|token|psk|private)", re.IGNORECASE)


@dataclass(frozen=True)
class PreparedHardware:
    """Resolved hardware input used by USB preflight and configuration output."""

    mode: str
    profile_name: str | None
    auto_detect: bool
    resolved: dict[str, Any]
    override_paths: tuple[str, ...]


@dataclass(frozen=True)
class GeneratedConfiguration:
    """The visible, current generated configuration directory."""

    current_directory: Path
    runtime_config: Path
    hardware_config: Path
    prepared: PreparedHardware


def _ensure_mapping(value: Any, description: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{description} must be a YAML mapping")
    return value


def load_yaml_mapping(path: Path, description: str) -> dict[str, Any]:
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigurationError(f"cannot parse {description}: {error}") from error
    return _ensure_mapping(parsed, description)


def parse_yaml_mapping(text: str, description: str) -> dict[str, Any]:
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConfigurationError(f"cannot parse {description}: {error}") from error
    return _ensure_mapping(parsed, description)


def atomic_yaml(path: Path, value: Mapping[str, Any]) -> None:
    """Serialize YAML safely, fsync it, then atomically make it visible."""

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.new")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            yaml.safe_dump(
                dict(value),
                output,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def discover_profiles(available_directory: Path) -> dict[str, Path]:
    """Return only YAML files physically contained by the installed directory."""

    try:
        root = available_directory.resolve(strict=True)
    except OSError as error:
        raise ConfigurationError(f"installed profile directory is unavailable: {error}") from error
    if not root.is_dir():
        raise ConfigurationError(f"installed profile directory is not a directory: {root}")

    discovered: dict[str, Path] = {}
    for candidate in sorted(available_directory.rglob("*")):
        if not candidate.is_file() or candidate.suffix.lower() not in _YAML_SUFFIXES:
            continue
        try:
            resolved = candidate.resolve(strict=True)
            relative = resolved.relative_to(root)
        except (OSError, ValueError):
            # A profile symlink pointing outside the image-owned directory is
            # not an installed profile the App is willing to activate.
            continue
        logical_name = relative.with_suffix("").as_posix()
        if logical_name in discovered:
            raise ConfigurationError(f"duplicate installed profile name: {logical_name}")
        discovered[logical_name] = resolved
    if not discovered:
        raise ConfigurationError(f"no YAML profiles found in {available_directory}")
    return discovered


def _profile_name(value: Any, profiles: Mapping[str, Path]) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigurationError("hardware.profile must be a non-empty installed profile name")
    # Do not normalize a user value before lookup. This makes traversal and
    # extension tricks fail rather than accidentally aliasing a real profile.
    if value.startswith("/") or "\\" in value or any(piece in {"", ".", ".."} for piece in value.split("/")):
        raise ConfigurationError("hardware.profile must be a discovered relative profile name")
    if value not in profiles:
        raise ConfigurationError(f"hardware.profile is not installed: {value}")
    return value


def deep_merge(base: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    """Merge maps recursively; every non-map, including a list, is replaced."""

    merged = copy.deepcopy(dict(base))
    for key, override_value in overrides.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(override_value, dict):
            merged[key] = deep_merge(existing, override_value)
        else:
            merged[key] = copy.deepcopy(override_value)
    return merged


def overridden_paths(value: Mapping[str, Any], prefix: str = "") -> tuple[str, ...]:
    paths: list[str] = []
    for key, child in value.items():
        component = str(key)
        path = f"{prefix}.{component}" if prefix else component
        if isinstance(child, dict):
            paths.extend(overridden_paths(child, path))
        elif not _SECRET_COMPONENT.search(component):
            paths.append(path)
    return tuple(paths)


def _assert_empty(value: Any, name: str) -> None:
    if value not in (None, "", {}, []):
        raise ConfigurationError(f"{name} is not valid in this hardware mode")


def _hardware_overrides(hardware: Mapping[str, Any]) -> dict[str, Any]:
    """Load UI YAML overrides, while accepting the pre-schema mapping shape."""

    raw_overrides = hardware.get("overrides_yaml")
    legacy_overrides = hardware.get("overrides", {})
    if raw_overrides not in (None, ""):
        if not isinstance(raw_overrides, str):
            raise ConfigurationError("hardware.overrides_yaml must be YAML text")
        if raw_overrides.strip():
            if legacy_overrides not in (None, "", {}, []):
                raise ConfigurationError("set either hardware.overrides_yaml or hardware.overrides, not both")
            return parse_yaml_mapping(raw_overrides, "hardware.overrides_yaml")
    return _ensure_mapping(legacy_overrides, "hardware.overrides")


def prepare_hardware(options: Mapping[str, Any], available_directory: Path) -> PreparedHardware:
    hardware = _ensure_mapping(options.get("hardware"), "hardware")
    mode = hardware.get("mode")
    if mode not in {"profile", "custom", "customized_profile"}:
        raise ConfigurationError("hardware.mode must be profile, custom, or customized_profile")

    profiles = discover_profiles(available_directory)
    profile_name: str | None = None
    auto_detect = hardware.get("auto_detect", False)
    if not isinstance(auto_detect, bool):
        raise ConfigurationError("hardware.auto_detect must be true or false")
    override_paths: tuple[str, ...] = ()
    if mode == "profile":
        profile_name = _profile_name(hardware.get("profile"), profiles)
        _assert_empty(hardware.get("config"), "hardware.config")
        _assert_empty(hardware.get("overrides"), "hardware.overrides")
        _assert_empty(hardware.get("overrides_yaml"), "hardware.overrides_yaml")
        resolved = load_yaml_mapping(profiles[profile_name], f"profile {profile_name}")
    elif mode == "custom":
        _assert_empty(hardware.get("profile"), "hardware.profile")
        _assert_empty(hardware.get("overrides"), "hardware.overrides")
        _assert_empty(hardware.get("overrides_yaml"), "hardware.overrides_yaml")
        custom = hardware.get("config")
        if not isinstance(custom, str) or not custom.strip():
            raise ConfigurationError("hardware.config must contain a complete YAML mapping in custom mode")
        resolved = parse_yaml_mapping(custom, "hardware.config")
        if auto_detect:
            raise ConfigurationError("hardware.auto_detect is not valid for custom mode")
    else:
        profile_name = _profile_name(hardware.get("profile"), profiles)
        _assert_empty(hardware.get("config"), "hardware.config")
        overrides = _hardware_overrides(hardware)
        resolved = deep_merge(
            load_yaml_mapping(profiles[profile_name], f"profile {profile_name}"), overrides
        )
        override_paths = overridden_paths(overrides)

    return PreparedHardware(
        mode=mode,
        profile_name=profile_name,
        auto_detect=auto_detect,
        resolved=resolved,
        override_paths=override_paths,
    )


def _symlink(target: Path | str, link: Path) -> None:
    link.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    link.symlink_to(target)


def _mirror_available_profiles(
    target_directory: Path,
    profiles: Mapping[str, Path],
    prepared: PreparedHardware,
    generated_hardware: Path,
) -> None:
    """Create a generated available.d tree without touching the image tree."""

    for name, source in profiles.items():
        destination = target_directory / f"{name}{source.suffix.lower()}"
        if prepared.mode == "customized_profile" and name == prepared.profile_name:
            _symlink(generated_hardware, destination)
        else:
            _symlink(source, destination)


def _safe_generation_id() -> str:
    return uuid.uuid4().hex


def _cleanup_old_generations(generated_directory: Path, current_target: Path) -> None:
    runs = generated_directory / "runs"
    entries = [entry for entry in runs.iterdir() if entry.is_dir() and entry != current_target]
    entries.sort(key=lambda entry: entry.stat().st_mtime, reverse=True)
    for old in entries[2:]:
        shutil.rmtree(old)


def generate_configuration(
    options: Mapping[str, Any],
    available_directory: Path,
    data_directory: Path,
    mac_address: str,
) -> GeneratedConfiguration:
    """Generate an isolated configuration tree and atomically select it."""

    prepared = prepare_hardware(options, available_directory)
    profiles = discover_profiles(available_directory)
    generation_root = data_directory / "generated"
    run = generation_root / "runs" / _safe_generation_id()
    run.mkdir(mode=0o700, parents=True)
    try:
        hardware_config = run / "hardware.yaml"
        if prepared.mode == "profile":
            # The active fragment is linked directly to installed upstream
            # content: no local stock-profile copy can get stale.
            hardware_config.unlink(missing_ok=True)
            _symlink(profiles[prepared.profile_name or ""], hardware_config)
        else:
            atomic_yaml(hardware_config, prepared.resolved)

        active = run / "active.d" / "10-hardware.yaml"
        if prepared.auto_detect:
            lora = _ensure_mapping(prepared.resolved.get("Lora"), "Lora in selected profile")
            # This is only an auto-detection locator. The selected profile's
            # full resolved YAML is in generated available.d and is loaded by
            # meshtasticd after matching the CH341 product string.
            locator = {"Lora": {"Module": "auto"}}
            for key in ("USB_VID", "USB_PID", "USB_Serialnum"):
                if key in lora:
                    locator["Lora"][key] = copy.deepcopy(lora[key])
            atomic_yaml(active, locator)
        else:
            _symlink(Path("../hardware.yaml"), active)
        available = run / "available.d"
        _mirror_available_profiles(available, profiles, prepared, hardware_config)

        # The official image supplies configuration fragments and defaults in
        # the binary; it does not include a monolithic /etc config.yaml.
        runtime: dict[str, Any] = {}
        general = runtime.setdefault("General", {})
        _ensure_mapping(general, "General in generated runtime configuration")
        general["MACAddress"] = mac_address
        general["ConfigDirectory"] = f"{run}/active.d/"
        general["AvailableDirectory"] = f"{run}/available.d/"
        # API access is internal only because config.yaml has no host mapping.
        # The Alpine meshtasticd image is a daemon image, not a bundled web
        # client.  The HA Meshtastic integration proxies this Stream API; do
        # not create an unrelated Webserver/TLS configuration here.
        general["TCPPort"] = 4403
        atomic_yaml(run / "runtime.yaml", runtime)

        temporary_link = generation_root / f".current.{uuid.uuid4().hex}.new"
        temporary_link.symlink_to(run.relative_to(generation_root))
        os.replace(temporary_link, generation_root / "current")
        _cleanup_old_generations(generation_root, run)
    except Exception:
        shutil.rmtree(run, ignore_errors=True)
        raise

    current = generation_root / "current"
    return GeneratedConfiguration(
        current_directory=current,
        runtime_config=current / "runtime.yaml",
        hardware_config=current / "hardware.yaml",
        prepared=prepared,
    )


def load_options(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigurationError(f"cannot parse Supervisor options: {error}") from error
    return _ensure_mapping(loaded, "Supervisor options")
