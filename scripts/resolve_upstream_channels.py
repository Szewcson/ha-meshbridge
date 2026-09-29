#!/usr/bin/env python3
"""Resolve independent mutable upstream channels by OCI digest only."""

from __future__ import annotations

import json
import re
import sys
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
CHANNELS = ("alpha", "beta")


def fetch_json(url: str, service: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "meshbridge-upstream-resolver/1"})
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


def load_upstream() -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(UPSTREAM_FILE.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise RuntimeError(f"cannot load upstream.yaml: {error}") from error
    if not isinstance(loaded, dict) or not isinstance(loaded.get("channels"), dict):
        raise RuntimeError("upstream.yaml must contain a channels mapping")
    return loaded


def revoked(release: dict[str, Any]) -> bool:
    values = (release.get("name"), release.get("body"))
    return any(isinstance(value, str) and "revoked" in value.casefold() for value in values)


def required_platforms(tag: dict[str, Any]) -> set[str]:
    images = tag.get("images")
    if not isinstance(images, list):
        raise RuntimeError("Docker Hub tag response has no images list")
    return {
        image.get("architecture")
        for image in images
        if isinstance(image, dict) and isinstance(image.get("architecture"), str)
    }


def main() -> int:
    try:
        upstream = load_upstream()
        required = upstream.get("required_platforms")
        if required != ["amd64", "arm64"]:
            raise RuntimeError("upstream.yaml must require amd64 and arm64")
        channels = upstream["channels"]
        result: dict[str, Any] = {"channels": {}}
        for channel in CHANNELS:
            stored = channels.get(channel)
            if not isinstance(stored, dict):
                raise RuntimeError(f"upstream.yaml is missing {channel}")
            image = stored.get("image")
            discovery_tag = stored.get("discovery_tag")
            digest = stored.get("digest")
            source_tag = stored.get("source_tag")
            if not all(isinstance(value, str) and value for value in (image, discovery_tag, digest, source_tag)):
                raise RuntimeError(f"upstream.yaml {channel} is incomplete")
            if discovery_tag != f"{channel}-alpine" or not DIGEST.fullmatch(digest):
                raise RuntimeError(f"upstream.yaml {channel} has invalid discovery metadata")

            current_release = fetch_json(GITHUB_RELEASE.format(tag=quote(source_tag)), f"GitHub {channel} release")
            if current_release.get("draft") is True or revoked(current_release):
                raise RuntimeError(f"currently pinned {channel} release {source_tag} is draft or revoked")

            tag = fetch_json(
                DOCKER_HUB_TAG.format(image=image, tag=quote(discovery_tag, safe="")),
                f"Docker Hub {channel} tag",
            )
            candidate_digest = tag.get("digest")
            if tag.get("name") != discovery_tag or not isinstance(candidate_digest, str) or not DIGEST.fullmatch(candidate_digest):
                raise RuntimeError(f"Docker Hub returned invalid {channel} tag metadata")
            platforms = required_platforms(tag)
            if not set(required).issubset(platforms):
                raise RuntimeError(f"{channel} tag lacks required platforms: expected {required}, found {sorted(platforms)}")
            result["channels"][channel] = {
                "channel": channel,
                "image": image,
                "discovery_tag": discovery_tag,
                "digest": candidate_digest,
                "platforms": sorted(platforms),
                "changed": candidate_digest != digest,
            }
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
