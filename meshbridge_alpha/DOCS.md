# MeshBridge Alpha

MeshBridge Alpha is an independent Home Assistant App wrapper for the
Meshtastic® `meshtasticd` Alpha Alpine daemon. It runs the official upstream
image without compiling, modifying, or claiming ownership of `meshtasticd`.

## Immutable provenance

`upstream.yaml` is the canonical source for the current wrapper version,
upstream mutable discovery tag, immutable release tag, OCI digest, daemon
version, fixed firmware release tag, and source URL. The Dockerfile is a
derived, validated copy of that information.

Current channel: **Alpha**. Beta is a separate channel and is never compared
numerically with Alpha.

## Connect Home Assistant

After configuration and startup, configure the Meshtastic integration with:

```text
Transport: TCP
Host: <installed App internal DNS name>
Port: 4403
```

Only the internal Stream API is configured. MeshBridge does not install web
assets, does not configure a `Webserver` section, and does not declare TCP
port 9443. The Home Assistant integration’s Web Client uses its own HTTP proxy
over the existing `meshtasticd` TCP connection.

## Hardware configuration

Use one of `profile`, `custom`, or `customized_profile` under `hardware`.
Profiles are discovered from upstream `/etc/meshtasticd/available.d`; they are
not copied into this repository. To customize a profile, supply YAML through
`hardware.overrides_yaml`. The App rejects ambiguous USB selection and validates
an exact serial before starting the daemon.

## Security

The App has no host network, privileged capabilities, Docker API, Home
Assistant API, or Supervisor API. It uses a dedicated AppArmor profile, raw USB
access supplied by Home Assistant, and an internal-only TCP `4403` declaration.
Raw USB is necessarily broader than the selected device: custom profiles and
YAML overrides are trusted administrator configuration. See
[SECURITY.md](../SECURITY.md) for the permission boundary and image verification
steps.

Meshtastic® is a registered trademark of Meshtastic LLC. Meshtastic software
components are released under various licenses; see the upstream project for
details. No warranty is provided - use at your own risk.

MeshBridge is an independent community project and is not affiliated with,
endorsed by, sponsored by, or supported by Meshtastic LLC or the Meshtastic
project. See the repository [LICENSE](../LICENSE) and
[third-party notices](../THIRD_PARTY_NOTICES.md).
