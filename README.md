# MeshBridge for Home Assistant

MeshBridge is an independent Home Assistant App wrapper for the Meshtastic®
`meshtasticd` daemon. It publishes separate experimental Alpha and Beta Apps
that use immutable, official upstream Alpine image pins.

| App | Slug | Wrapper image | Upstream stream |
| --- | --- | --- | --- |
| MeshBridge Beta | `meshbridge_beta` | `ghcr.io/szewcson/meshbridge-beta` | `beta-alpine` |
| MeshBridge Alpha | `meshbridge_alpha` | `ghcr.io/szewcson/meshbridge-alpha` | `alpha-alpine` |

The streams are independent; Alpha and Beta version numbers are never compared
to decide which is newer or preferable. Do not run both Apps against one USB
radio.

## Install

This repository requires Home Assistant OS or a supported Supervised
installation.

1. Rename the GitHub repository to `ha-meshbridge` before adding it to Home
   Assistant.
2. In **Settings → Apps → App Store → Repositories**, add
   `https://github.com/Szewcson/ha-meshbridge` and refresh the store.
3. Enable experimental Apps in the Home Assistant user profile.
4. Install **MeshBridge Beta** or **MeshBridge Alpha**, configure its USB
   hardware profile, then start it.

## First package publication

After the breaking repository rename, run **Actions → Bootstrap MeshBridge
packages** once and select `publish`. It creates the initial `1.0.0` images in
the new GHCR namespace only when those immutable tags do not already exist.
This is deliberately separate from upstream synchronization: the scheduled
workflow must not rebuild or republish unchanged upstream digests.

For a versioned wrapper-only fix, use **Actions → Publish MeshBridge
maintenance release** and select `publish`. It retains the same immutable-tag
and multi-architecture verification safeguards.

The daemon’s Stream API is available only on the internal App network at TCP
port `4403`. MeshBridge does not install a web frontend or configure port 9443;
the Home Assistant Meshtastic integration’s web client must use its own proxy.

## Provenance and licensing

The canonical immutable upstream pins and release-source links are in
[upstream.yaml](upstream.yaml). MeshBridge wrapper code is MIT-licensed; the
upstream daemon remains GPL-3.0-only. See [LICENSE](LICENSE) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Meshtastic® is a registered trademark of Meshtastic LLC. Meshtastic software
components are released under various licenses; see the upstream project for
details. No warranty is provided - use at your own risk.

MeshBridge is an independent community project and is not affiliated with,
endorsed by, sponsored by, or supported by Meshtastic LLC or the Meshtastic
project.
