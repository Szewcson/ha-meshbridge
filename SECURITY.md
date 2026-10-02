# Security policy

## Scope and threat model

MeshBridge runs the upstream `meshtasticd` daemon as a Home Assistant App. It
does not expose a host-network listener, request Home Assistant, Supervisor, or
Docker APIs, or use privileged capabilities. The only daemon API listener is
TCP `4403` on the internal App network.

USB access is intentionally different: Home Assistant's `usb: true` permission
maps the host's raw USB bus into the App so the selected radio can be opened.
The wrapper validates the configured serial selection before daemon startup,
but raw USB access cannot be narrowed to one device dynamically by an AppArmor
path rule. Treat an administrator-supplied custom profile or YAML override as
trusted configuration. Do not install this App on a Home Assistant host where
other attached USB devices are outside the App administrator's trust boundary.

The upstream image is discovered through mutable channel tags, then pinned by
full OCI digest. Before publication the candidate must have amd64 and arm64
images, start the daemon simulator, provide TCP `4403`, resolve to its immutable
release tag, and match a non-draft, non-revoked Meshtastic firmware release.

## Release controls

Create a GitHub Actions environment named `meshbridge-release` in the
repository settings, then configure it as follows:

1. Require at least one reviewer who is not an everyday contributor.
2. Limit deployment branches to protected `main`.
3. Disable administrator bypass if your GitHub plan permits it.
4. Protect `main`, require passing **Validate MeshBridge**, and require review
   from the owners in [`.github/CODEOWNERS`](.github/CODEOWNERS).

The scheduled workflow checks both channel tags every six hours with only
read permission. When a digest changes it waits on that environment, validates
the replacement, records the immutable pin, and publishes the two Apps. The
same environment protects manual bootstrap and maintenance releases. This
keeps automatic monitoring while preventing an unreviewed mutable upstream tag
from immediately becoming a public MeshBridge release.

## Verify a published image

Final multi-architecture manifests are signed keylessly with GitHub Actions
OIDC after their platforms and digest have been verified. With Cosign installed:

```sh
cosign verify \
  --certificate-oidc-issuer=https://token.actions.githubusercontent.com \
  --certificate-identity-regexp='^https://github\.com/Szewcson/ha-meshbridge/' \
  ghcr.io/szewcson/meshbridge-alpha:<version>
```

Use `meshbridge-beta:<version>` for Beta. Home Assistant's `signed` field is
not a report of this Cosign signature; it uses a different trust mechanism.

## Reporting a vulnerability

Please use GitHub's private vulnerability-reporting facility for this
repository, or open a private contact channel with the repository maintainer.
Do not include secrets, device identifiers, or a working exploit in a public
issue.
