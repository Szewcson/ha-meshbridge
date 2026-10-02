#!/usr/bin/env python3
"""Validate MeshBridge branding, provenance, and generated App metadata."""

from __future__ import annotations

import re
import hashlib
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CHANNELS = {
    "beta": {
        "directory": "meshbridge_beta",
        "name": "MeshBridge Beta",
        "slug": "meshbridge_beta",
        "image": "ghcr.io/szewcson/meshbridge-beta",
    },
    "alpha": {
        "directory": "meshbridge_alpha",
        "name": "MeshBridge Alpha",
        "slug": "meshbridge_alpha",
        "image": "ghcr.io/szewcson/meshbridge-alpha",
    },
}
FORBIDDEN_BRANDING = (
    "meshtasticd" + " home assistant apps",
    "meshtasticd" + " beta",
    "meshtasticd" + " alpha",
    "ha-" + "meshtasticd",
    "meshtastic" + " gateway",
    "meshtastic" + " bridge",
    "meshtasticd" + "-beta",
    "meshtasticd" + "-alpha",
)
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
VERSION = re.compile(r"^\d+\.\d+\.\d+\.[0-9a-f]+$")
GPL_LICENSE_SHA256 = "0ae0485a5bd37a63e63603596417e4eb0e653334fa6c7f932ca3a0e85d4af227"


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def load_yaml(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        fail(errors, f"cannot load {path.relative_to(ROOT)}: {error}")
        return {}
    if not isinstance(loaded, dict):
        fail(errors, f"{path.relative_to(ROOT)} must contain a mapping")
        return {}
    return loaded


def check_branding(errors: list[str]) -> None:
    ignored_parts = {".git", ".pytest_cache", "__pycache__"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or ignored_parts.intersection(path.parts):
            continue
        if path.suffix in {".pyc", ".zip"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lowered = content.casefold()
        for forbidden in FORBIDDEN_BRANDING:
            if forbidden in lowered:
                fail(errors, f"obsolete branding {forbidden!r} in {path.relative_to(ROOT)}")


def check_required_files(errors: list[str]) -> None:
    for relative in ("LICENSE", "THIRD_PARTY_NOTICES.md", "licenses/Meshtastic-GPL-3.0.txt", "upstream.yaml"):
        if not (ROOT / relative).is_file():
            fail(errors, f"required file is missing: {relative}")
    try:
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        if not license_text.startswith("MIT License\n"):
            fail(errors, "LICENSE must grant MIT terms for MeshBridge wrapper code")
        notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        for required_notice in (
            "https://github.com/meshtastic/firmware",
            "Component: `meshtasticd`",
            "GNU General Public License v3",
            "does not claim ownership",
        ):
            if required_notice not in notice:
                fail(errors, f"THIRD_PARTY_NOTICES.md is missing required provenance: {required_notice}")
        gpl = (ROOT / "licenses/Meshtastic-GPL-3.0.txt").read_bytes()
        if hashlib.sha256(gpl).hexdigest() != GPL_LICENSE_SHA256:
            fail(errors, "licenses/Meshtastic-GPL-3.0.txt is not the exact upstream license text")
    except OSError as error:
        fail(errors, f"cannot inspect required legal notice: {error}")


def check_channel(channel: str, metadata: dict[str, Any], errors: list[str]) -> None:
    expected = CHANNELS[channel]
    directory = ROOT / expected["directory"]
    config = load_yaml(directory / "config.yaml", errors)
    for key in ("name", "slug", "image", "version"):
        if not isinstance(config.get(key), str):
            fail(errors, f"{directory.name}/config.yaml has no string {key}")
    for key in ("name", "slug", "image"):
        if config.get(key) != expected[key]:
            fail(errors, f"{directory.name}/config.yaml {key} does not match {expected[key]!r}")
    if config.get("version") != metadata.get("app_version"):
        fail(errors, f"{directory.name}/config.yaml version is not derived from upstream.yaml")
    if config.get("stage") != "experimental":
        fail(errors, f"{directory.name}/config.yaml must remain experimental")
    if config.get("arch") != ["amd64", "aarch64"]:
        fail(errors, f"{directory.name}/config.yaml has an unexpected published architecture set")
    if config.get("ports") != {"4403/tcp": None}:
        fail(errors, f"{directory.name}/config.yaml must only declare internal TCP port 4403")
    if "Webserver" in config or "9443/tcp" in config.get("ports", {}):
        fail(errors, f"{directory.name}/config.yaml must not configure the Alpine web server")

    for key in ("image", "discovery_tag", "pinned_tag", "version", "digest", "source_tag", "source_url"):
        if not isinstance(metadata.get(key), str) or not metadata[key]:
            fail(errors, f"upstream.yaml {channel} has no valid {key}")
    if metadata.get("image") != "meshtastic/meshtasticd":
        fail(errors, f"upstream.yaml {channel} must use the official meshtasticd image")
    if metadata.get("discovery_tag") != f"{channel}-alpine":
        fail(errors, f"upstream.yaml {channel} has an invalid mutable discovery tag")
    if not DIGEST.fullmatch(str(metadata.get("digest", ""))):
        fail(errors, f"upstream.yaml {channel} has an invalid OCI digest")
    if not VERSION.fullmatch(str(metadata.get("version", ""))):
        fail(errors, f"upstream.yaml {channel} has an invalid daemon version")
    if metadata.get("pinned_tag") != f"{metadata.get('version')}-{channel}-alpine":
        fail(errors, f"upstream.yaml {channel} pinned tag is not tied to the resolved daemon version")
    if metadata.get("source_tag") != f"v{metadata.get('version')}":
        fail(errors, f"upstream.yaml {channel} source tag is not an exact upstream release tag")
    if metadata.get("source_url") != f"https://github.com/meshtastic/firmware/releases/tag/{metadata.get('source_tag')}":
        fail(errors, f"upstream.yaml {channel} source URL is not an exact upstream release URL")

    dockerfile = (directory / "Dockerfile").read_text(encoding="utf-8")
    expected_from = f"FROM {metadata['image']}:{metadata['pinned_tag']}@{metadata['digest']}"
    if expected_from not in dockerfile:
        fail(errors, f"{directory.name}/Dockerfile does not use the upstream.yaml immutable pin")
    required_labels = (
        'org.opencontainers.image.source="https://github.com/Szewcson/ha-meshbridge"',
        'org.opencontainers.image.licenses="MIT AND GPL-3.0-only"',
        'io.meshbridge.upstream.name="meshtasticd"',
        f'io.meshbridge.upstream.channel="{channel}"',
        f'ARG UPSTREAM_MESHTASTICD_VERSION={metadata["version"]}',
        f'ARG UPSTREAM_MESHTASTICD_TAG={metadata["pinned_tag"]}',
        f'ARG UPSTREAM_MESHTASTICD_DIGEST={metadata["digest"]}',
        f'ARG UPSTREAM_SOURCE_URL={metadata["source_url"]}',
        f'io.meshbridge.upstream.version="${{UPSTREAM_MESHTASTICD_VERSION}}"',
        f'io.meshbridge.upstream.digest="${{UPSTREAM_MESHTASTICD_DIGEST}}"',
        f'io.meshbridge.upstream.source="${{UPSTREAM_SOURCE_URL}}"',
        f'ARG MESHBRIDGE_VERSION={metadata["app_version"]}',
        'HEALTHCHECK --interval=5s --timeout=2s --start-period=35s --retries=3 CMD ["/usr/local/bin/meshbridge-listener-ready"]',
    )
    for label in required_labels:
        if label not in dockerfile:
            fail(errors, f"{directory.name}/Dockerfile is missing derived metadata: {label}")


def main() -> int:
    errors: list[str] = []
    check_required_files(errors)
    check_branding(errors)
    upstream = load_yaml(ROOT / "upstream.yaml", errors)
    channels = upstream.get("channels")
    if upstream.get("schema_version") != 1 or not isinstance(channels, dict):
        fail(errors, "upstream.yaml must have schema_version 1 and a channels mapping")
        channels = {}
    if upstream.get("source_repository") != "https://github.com/meshtastic/firmware":
        fail(errors, "upstream.yaml must identify the fixed upstream repository")
    if upstream.get("required_platforms") != ["amd64", "arm64"]:
        fail(errors, "upstream.yaml must require amd64 and arm64 upstream platforms")
    for channel in CHANNELS:
        metadata = channels.get(channel)
        if not isinstance(metadata, dict):
            fail(errors, f"upstream.yaml is missing the {channel} channel")
            continue
        if metadata.get("app_directory") != CHANNELS[channel]["directory"]:
            fail(errors, f"upstream.yaml {channel} App directory is incorrect")
        if not re.fullmatch(r"\d+\.\d+\.\d+", str(metadata.get("app_version", ""))):
            fail(errors, f"upstream.yaml {channel} App version is invalid")
        check_channel(channel, metadata, errors)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
