# Third-party notices

## Meshtastic firmware / meshtasticd

- Upstream: <https://github.com/meshtastic/firmware>
- Component: `meshtasticd`
- License: GNU General Public License v3.0 only

MeshBridge redistributes the official upstream `meshtasticd` container as a
base image and does not claim ownership of `meshtasticd`. Its exact immutable
image pin, daemon version, source release, and source URL are recorded in
[upstream.yaml](upstream.yaml). The upstream GPL-3.0 text is reproduced in
[licenses/Meshtastic-GPL-3.0.txt](licenses/Meshtastic-GPL-3.0.txt).

The independently authored MeshBridge wrapper code is MIT-licensed; that grant
does not apply to components inherited from the upstream container image.

## Wrapper source audit

The MeshBridge launcher, USB selection, configuration generation, AppArmor
profile, and CI code in this repository were reviewed for this release. They
do not copy or substantially adapt Meshtastic GPL source files; the upstream
daemon is consumed only as the documented container base image above.
