"""Regression tests for release-pipeline validation scripts."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType


REPOSITORY = Path(__file__).resolve().parents[1]


def load_script(name: str) -> ModuleType:
    path = REPOSITORY / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_resolver_can_replace_a_revoked_pin(monkeypatch, tmp_path: Path, capsys) -> None:
    """A historical revocation must not block discovery of its replacement."""

    resolver = load_script("resolve_upstream_channels")
    upstream = {
        "required_platforms": ["amd64", "arm64"],
        "channels": {
            channel: {
                "image": "meshtastic/meshtasticd",
                "discovery_tag": f"{channel}-alpine",
                "digest": "sha256:" + ("a" if channel == "alpha" else "b") * 64,
                "source_tag": "v2.8.0.revoked",
            }
            for channel in ("alpha", "beta")
        },
    }
    upstream_file = tmp_path / "upstream.yaml"
    upstream_file.write_text(resolver.yaml.safe_dump(upstream), encoding="utf-8")
    monkeypatch.setattr(resolver, "UPSTREAM_FILE", upstream_file)

    requests: list[str] = []

    def fake_fetch_json(url: str, service: str) -> dict[str, object]:
        requests.append(url)
        channel = "alpha" if "alpha-alpine" in url else "beta"
        return {
            "name": f"{channel}-alpine",
            "digest": "sha256:" + ("c" if channel == "alpha" else "b") * 64,
            "images": [{"architecture": "amd64"}, {"architecture": "arm64"}],
        }

    monkeypatch.setattr(resolver, "fetch_json", fake_fetch_json)

    assert resolver.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["channels"]["alpha"]["changed"] is True
    assert result["channels"]["beta"]["changed"] is False
    assert all("hub.docker.com" in url for url in requests)


def test_validator_checks_beta_channel(monkeypatch, tmp_path: Path, capsys) -> None:
    """Both public Apps must be rejected if either metadata set drifts."""

    repository = tmp_path / "repository"
    shutil.copytree(
        REPOSITORY,
        repository,
        ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__"),
    )
    config = repository / "meshbridge_beta" / "config.yaml"
    config.write_text(
        config.read_text(encoding="utf-8").replace("stage: experimental", "stage: stable"),
        encoding="utf-8",
    )
    validator = load_script("validate_meshbridge")
    monkeypatch.setattr(validator, "ROOT", repository)

    assert validator.main() == 1
    assert "meshbridge_beta/config.yaml must remain experimental" in capsys.readouterr().err


def test_release_workflows_keep_their_security_boundaries() -> None:
    """Regression-check permissions, dependency locking, and image signing."""

    sync = (REPOSITORY / ".github/workflows/sync-upstream-images.yaml").read_text(encoding="utf-8")
    publish = (REPOSITORY / ".github/workflows/publish-app.yaml").read_text(encoding="utf-8")
    requirements = (REPOSITORY / ".github/requirements/sync-requirements.txt").read_text(encoding="utf-8")

    assert "environment: meshbridge-release" in sync
    assert "--require-hashes" in sync
    assert "contents: write" in sync
    assert "alpha_changed: ${{ steps.channels.outputs.alpha }}" in sync
    assert "beta_changed: ${{ steps.channels.outputs.beta }}" in sync
    assert "needs.sync.outputs.alpha_changed == 'true'" in sync
    assert "needs.sync.outputs.beta_changed == 'true'" in sync
    assert "id-token: write" not in sync.split("jobs:", 1)[0]
    assert "PyYAML==6.0.2" in requirements
    assert "--hash=sha256:" in requirements
    assert "environment: meshbridge-release" in (
        REPOSITORY / ".github/workflows/publish-maintenance-release.yaml"
    ).read_text(encoding="utf-8")
    assert "sigstore/cosign-installer@ba7bc0a3fef59531c69a25acd34668d6d3fe6f22" in publish
    assert "cosign sign --yes" in publish
    assert "cosign verify" in publish
    assert "--certificate-identity='https://github.com/Szewcson/ha-meshbridge/.github/workflows/publish-app.yaml@refs/heads/main'" in publish


def test_upstream_smoke_keeps_simulator_files_runner_owned() -> None:
    """The cleanup trap must not fail after a successful candidate test."""

    smoke = (REPOSITORY / "scripts/smoke_upstream_candidate.sh").read_text(encoding="utf-8")
    assert 'runner_uid=$(id -u)' in smoke
    assert 'runner_gid=$(id -g)' in smoke
    assert '--user "${runner_uid}:${runner_gid}"' in smoke
    assert 'rm -rf -- "$test_directory" || echo "warning:' in smoke
