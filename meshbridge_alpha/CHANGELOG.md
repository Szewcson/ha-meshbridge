# Changelog

## 1.0.1

- Replace the inherited `HEALTHCHECK NONE` metadata with a local readiness
  check for the Meshtastic TCP API listener. This allows Home Assistant
  Supervisor to transition the App from `startup` to `started`.

## 1.0.0

- Breaking rename to MeshBridge Alpha with the `meshbridge_alpha` Home
  Assistant App slug and `ghcr.io/szewcson/meshbridge-alpha` wrapper image.
- Record exact upstream provenance in `upstream.yaml` and publish only an
  immutable `meshtasticd` digest pin.
