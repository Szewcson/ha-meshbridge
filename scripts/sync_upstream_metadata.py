#!/usr/bin/env python3
"""Apply smoke-tested immutable upstream metadata from the canonical YAML file."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import yaml


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_FILE = ROOT / "upstream.yaml"
DOCKER_HUB_TAG = "https://hub.docker.com/v2/repositories/{image}/tags/{tag}"
GITHUB_RELEASE = "https://api.github.com/repos/meshtastic/firmware/releases/tags/{tag}"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
DAEMON_VERSION = re.compile(r"^\d+\.\d+\.\d+\.[0-9a-f]+$")
APP_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
CHANNELS = ("alpha", "beta")


def fetch_json(url: str, service: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "meshbridge-upstream-sync/1"})
    try:
        with urlopen(request, timeout=20) as response:  # nosec B310: fixed official HTTPS origins
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError) as error:
        raise RuntimeError(f"{service} query failed: {error}") from error
    if len(raw) > MAX_RESPONSE_BYTES:
        raise RuntimeError(f"{service} response exceeded {MAX_RESPONSE_BYTES} bytes")
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{service} returned invalid JSON") from error
    if not isinstance(loaded, dict):
        raise RuntimeError(f"{service} returned an invalid response shape")
    return loaded


def write_atomic(path: Path, content: str) -> None:
    mode = path.stat().st_mode
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    try:
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def bump_patch(version: str) -> str:
    match = APP_VERSION.fullmatch(version)
    if not match:
        raise RuntimeError(f"invalid MeshBridge App version: {version}")
    major, minor, patch = (int(value) for value in match.groups())
    return f"{major}.{minor}.{patch + 1}"


def revoked(release: dict[str, Any]) -> bool:
    # Release notes may discuss a different revoked build. The release title
    # is the canonical human-visible status for the release being validated.
    name = release.get("name")
    return isinstance(name, str) and "revoked" in name.casefold()


def platforms(tag: dict[str, Any]) -> set[str]:
    images = tag.get("images")
    if not isinstance(images, list):
        raise RuntimeError("Docker Hub response has no images list")
    return {
        image.get("architecture")
        for image in images
        if isinstance(image, dict) and isinstance(image.get("architecture"), str)
    }


def render_dockerfile(channel: str, metadata: dict[str, str]) -> str:
    app_name = f"MeshBridge {channel.title()}"
    return f'''# syntax=docker/dockerfile:1
# Generated from upstream.yaml; validate with scripts/validate_meshbridge.py.
FROM {metadata["image"]}:{metadata["pinned_tag"]}@{metadata["digest"]}

ARG BUILD_ARCH=amd64
ARG MESHBRIDGE_VERSION={metadata["app_version"]}
ARG UPSTREAM_MESHTASTICD_VERSION={metadata["version"]}
ARG UPSTREAM_MESHTASTICD_TAG={metadata["pinned_tag"]}
ARG UPSTREAM_MESHTASTICD_DIGEST={metadata["digest"]}
ARG UPSTREAM_SOURCE_URL={metadata["source_url"]}

ENV PYTHONSAFEPATH=1 \\
    PYTHONDONTWRITEBYTECODE=1

LABEL \\
    io.hass.name="{app_name}" \\
    io.hass.description="Independent Home Assistant App wrapper for the Meshtastic meshtasticd daemon" \\
    io.hass.type="app" \\
    io.hass.version="${{MESHBRIDGE_VERSION}}" \\
    io.hass.arch="${{BUILD_ARCH}}" \\
    org.opencontainers.image.version="${{MESHBRIDGE_VERSION}}" \\
    org.opencontainers.image.source="https://github.com/Szewcson/ha-meshbridge" \\
    org.opencontainers.image.revision="${{UPSTREAM_MESHTASTICD_VERSION}}" \\
    org.opencontainers.image.licenses="MIT AND GPL-3.0-only" \\
    org.opencontainers.image.base.name="meshtastic/meshtasticd:${{UPSTREAM_MESHTASTICD_TAG}}" \\
    org.opencontainers.image.base.digest="${{UPSTREAM_MESHTASTICD_DIGEST}}" \\
    io.meshbridge.upstream.name="meshtasticd" \\
    io.meshbridge.upstream.repository="https://github.com/meshtastic/firmware" \\
    io.meshbridge.upstream.channel="{channel}" \\
    io.meshbridge.upstream.version="${{UPSTREAM_MESHTASTICD_VERSION}}" \\
    io.meshbridge.upstream.digest="${{UPSTREAM_MESHTASTICD_DIGEST}}" \\
    io.meshbridge.upstream.source="${{UPSTREAM_SOURCE_URL}}"

RUN apk add --no-cache \\
    py3-usb \\
    py3-yaml \\
    python3

RUN printf 'app_version=%s\\nupstream_version=%s\\nupstream_tag=%s\\nupstream_digest=%s\\nupstream_source=%s\\n' \\
    "${{MESHBRIDGE_VERSION}}" "${{UPSTREAM_MESHTASTICD_VERSION}}" "${{UPSTREAM_MESHTASTICD_TAG}}" \\
    "${{UPSTREAM_MESHTASTICD_DIGEST}}" "${{UPSTREAM_SOURCE_URL}}" \\
    > /etc/meshbridge-release

COPY rootfs /
COPY run.sh /run.sh

RUN chmod 0755 /run.sh /usr/local/bin/meshbridge-listener-ready \\
    && chmod 0644 /usr/local/lib/meshbridge_app/*.py

# The upstream Alpine image has `HEALTHCHECK NONE`, which is represented in
# Docker metadata as a non-empty object. Home Assistant Supervisor therefore
# waits for it forever. Replace it with a local, AppArmor-permitted readiness
# test for the daemon API listener.
HEALTHCHECK --interval=5s --timeout=2s --start-period=35s --retries=3 CMD ["/usr/local/bin/meshbridge-listener-ready"]

CMD [ "/run.sh" ]
'''


def replace_version(config: Path, version: str) -> str:
    content = config.read_text(encoding="utf-8")
    updated, count = re.subn(r'^version: "[^"]+"$', f'version: "{version}"', content, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"cannot update version in {config}")
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("versions", type=Path)
    arguments = parser.parse_args()
    try:
        upstream = yaml.safe_load(UPSTREAM_FILE.read_text(encoding="utf-8"))
        candidates = json.loads(arguments.candidates.read_text(encoding="utf-8"))
        versions = json.loads(arguments.versions.read_text(encoding="utf-8"))
        if not isinstance(upstream, dict) or not isinstance(upstream.get("channels"), dict):
            raise RuntimeError("upstream.yaml must contain channels")
        if not isinstance(candidates, dict) or not isinstance(candidates.get("channels"), dict):
            raise RuntimeError("candidate data must contain channels")
        if not isinstance(versions, dict):
            raise RuntimeError("smoke-test version data must be an object")

        updates: dict[str, dict[str, str]] = {}
        for channel in CHANNELS:
            candidate = candidates["channels"].get(channel)
            if not isinstance(candidate, dict) or candidate.get("changed") is not True:
                continue
            daemon_version = versions.get(channel)
            image = candidate.get("image")
            digest = candidate.get("digest")
            discovery_tag = candidate.get("discovery_tag")
            if not isinstance(daemon_version, str) or not DAEMON_VERSION.fullmatch(daemon_version):
                raise RuntimeError(f"smoke test did not return a valid {channel} daemon version")
            if (
                candidate.get("channel") != channel
                or discovery_tag != f"{channel}-alpine"
                or not isinstance(image, str)
                or image != "meshtastic/meshtasticd"
                or not isinstance(digest, str)
                or not DIGEST.fullmatch(digest)
            ):
                raise RuntimeError(f"candidate {channel} metadata is invalid")
            pinned_tag = f"{daemon_version}-{channel}-alpine"
            tag = fetch_json(DOCKER_HUB_TAG.format(image=image, tag=quote(pinned_tag, safe="")), f"Docker Hub {channel} pin")
            if tag.get("name") != pinned_tag or tag.get("digest") != digest:
                raise RuntimeError(f"candidate {channel} immutable tag does not match its discovered digest")
            if not {"amd64", "arm64"}.issubset(platforms(tag)):
                raise RuntimeError(f"candidate {channel} immutable tag lacks amd64 or arm64")
            source_tag = f"v{daemon_version}"
            release = fetch_json(GITHUB_RELEASE.format(tag=quote(source_tag)), f"GitHub {channel} release")
            if release.get("draft") is True or revoked(release):
                raise RuntimeError(f"candidate {channel} release {source_tag} is draft or revoked")
            stored = upstream["channels"].get(channel)
            if (
                not isinstance(stored, dict)
                or stored.get("app_directory") != f"meshbridge_{channel}"
                or not isinstance(stored.get("app_version"), str)
            ):
                raise RuntimeError(f"upstream.yaml {channel} is incomplete")
            updates[channel] = {
                "app_directory": str(stored.get("app_directory")),
                "app_version": bump_patch(stored["app_version"]),
                "image": image,
                "discovery_tag": f"{channel}-alpine",
                "pinned_tag": pinned_tag,
                "version": daemon_version,
                "digest": digest,
                "source_tag": source_tag,
                "source_url": f"https://github.com/meshtastic/firmware/releases/tag/{source_tag}",
            }

        if not updates:
            print(json.dumps({"changed_apps": []}, sort_keys=True))
            return 0
        for channel, metadata in updates.items():
            upstream["channels"][channel] = metadata

        rendered: list[tuple[Path, str]] = [(UPSTREAM_FILE, yaml.safe_dump(upstream, sort_keys=False))]
        for channel, metadata in updates.items():
            directory = ROOT / metadata["app_directory"]
            rendered.append((directory / "Dockerfile", render_dockerfile(channel, metadata)))
            rendered.append((directory / "config.yaml", replace_version(directory / "config.yaml", metadata["app_version"])))
        for path, content in rendered:
            write_atomic(path, content)
    except (OSError, RuntimeError, ValueError, yaml.YAMLError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(json.dumps({"changed_apps": [updates[channel]["app_directory"] for channel in sorted(updates)]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
