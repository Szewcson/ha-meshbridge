# syntax=docker/dockerfile:1
# Generated from upstream.yaml; validate with scripts/validate_meshbridge.py.
FROM meshtastic/meshtasticd:2.8.1.8e6a88d-alpha-alpine@sha256:a938085c84ea734229622bb654291d08c2b68c23a57c6e1966eef0b749db5459

ARG BUILD_ARCH=amd64
ARG MESHBRIDGE_VERSION=1.0.2
ARG UPSTREAM_MESHTASTICD_VERSION=2.8.1.8e6a88d
ARG UPSTREAM_MESHTASTICD_TAG=2.8.1.8e6a88d-alpha-alpine
ARG UPSTREAM_MESHTASTICD_DIGEST=sha256:a938085c84ea734229622bb654291d08c2b68c23a57c6e1966eef0b749db5459
ARG UPSTREAM_SOURCE_URL=https://github.com/meshtastic/firmware/releases/tag/v2.8.1.8e6a88d

ENV PYTHONSAFEPATH=1 \
    PYTHONDONTWRITEBYTECODE=1

LABEL \
    io.hass.name="MeshBridge Alpha" \
    io.hass.description="Independent Home Assistant App wrapper for the Meshtastic meshtasticd daemon" \
    io.hass.type="app" \
    io.hass.version="${MESHBRIDGE_VERSION}" \
    io.hass.arch="${BUILD_ARCH}" \
    org.opencontainers.image.version="${MESHBRIDGE_VERSION}" \
    org.opencontainers.image.source="https://github.com/Szewcson/ha-meshbridge" \
    org.opencontainers.image.revision="${UPSTREAM_MESHTASTICD_VERSION}" \
    org.opencontainers.image.licenses="MIT AND GPL-3.0-only" \
    org.opencontainers.image.base.name="meshtastic/meshtasticd:${UPSTREAM_MESHTASTICD_TAG}" \
    org.opencontainers.image.base.digest="${UPSTREAM_MESHTASTICD_DIGEST}" \
    io.meshbridge.upstream.name="meshtasticd" \
    io.meshbridge.upstream.repository="https://github.com/meshtastic/firmware" \
    io.meshbridge.upstream.channel="alpha" \
    io.meshbridge.upstream.version="${UPSTREAM_MESHTASTICD_VERSION}" \
    io.meshbridge.upstream.digest="${UPSTREAM_MESHTASTICD_DIGEST}" \
    io.meshbridge.upstream.source="${UPSTREAM_SOURCE_URL}"

RUN apk add --no-cache \
    py3-usb \
    py3-yaml \
    python3

RUN printf 'app_version=%s\nupstream_version=%s\nupstream_tag=%s\nupstream_digest=%s\nupstream_source=%s\n' \
    "${MESHBRIDGE_VERSION}" "${UPSTREAM_MESHTASTICD_VERSION}" "${UPSTREAM_MESHTASTICD_TAG}" \
    "${UPSTREAM_MESHTASTICD_DIGEST}" "${UPSTREAM_SOURCE_URL}" \
    > /etc/meshbridge-release

COPY rootfs /
COPY run.sh /run.sh

RUN chmod 0755 /run.sh /usr/local/bin/meshbridge-listener-ready \
    && chmod 0644 /usr/local/lib/meshbridge_app/*.py

# The upstream Alpine image has `HEALTHCHECK NONE`, which is represented in
# Docker metadata as a non-empty object. Home Assistant Supervisor therefore
# waits for it forever. Replace it with a local, AppArmor-permitted readiness
# test for the daemon API listener.
HEALTHCHECK --interval=5s --timeout=2s --start-period=35s --retries=3 CMD ["/usr/local/bin/meshbridge-listener-ready"]

CMD [ "/run.sh" ]
