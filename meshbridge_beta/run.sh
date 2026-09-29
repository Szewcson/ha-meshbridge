#!/bin/sh
set -eu

readonly APP_DATA=/data
readonly GENERATED_CONFIG="${APP_DATA}/generated/current/runtime.yaml"
readonly MESHBRIDGE_STATE="${APP_DATA}/meshbridge-state"
readonly STOP_TIMEOUT_SECONDS=30

child_pid=""

log_info() {
    printf '%s\n' "INFO: $*" >&2
}

log_warning() {
    printf '%s\n' "WARNING: $*" >&2
}

log_error() {
    printf '%s\n' "ERROR: $*" >&2
}

stop_child() {
    if [ -z "${child_pid}" ] || ! kill -0 "${child_pid}" 2>/dev/null; then
        return
    fi

    log_info "Stopping meshtasticd"
    kill -TERM "${child_pid}"
    remaining="${STOP_TIMEOUT_SECONDS}"
    while kill -0 "${child_pid}" 2>/dev/null && [ "${remaining}" -gt 0 ]; do
        sleep 1
        remaining=$((remaining - 1))
    done
    if kill -0 "${child_pid}" 2>/dev/null; then
        log_warning "meshtasticd did not stop within ${STOP_TIMEOUT_SECONDS}s; sending SIGKILL"
        kill -KILL "${child_pid}"
    fi
    wait "${child_pid}" 2>/dev/null || true
    child_pid=""
}

trap 'stop_child; exit 0' TERM INT

mkdir -p "${MESHBRIDGE_STATE}"
PYTHONPATH=/usr/local/lib python3 -m meshbridge_app.launcher \
    --options "${APP_DATA}/options.json" \
    --available-dir /etc/meshtasticd/available.d \
    --data-dir "${APP_DATA}"

log_info "MeshBridge runtime generated: meshtasticd TCP API port 4403; embedded Webserver disabled; config=${GENERATED_CONFIG}"
log_info "Installed meshtasticd version:"
if ! /usr/bin/meshtasticd --version >&2; then
    log_warning "meshtasticd did not report a version; continuing with the pinned daemon"
fi

log_info "Starting pinned upstream meshtasticd with generated configuration"
/usr/bin/meshtasticd --config "${GENERATED_CONFIG}" --fsdir "${MESHBRIDGE_STATE}" &
child_pid="$!"

# This only inspects /proc; it neither connects to the API nor touches the
# radio. A process that exits before the listener appears is always a failure.
listener_ready=0
attempt=0
while [ "${attempt}" -lt 30 ]; do
    if ! kill -0 "${child_pid}" 2>/dev/null; then
        if wait "${child_pid}"; then
            exit 0
        else
            exit $?
        fi
    fi
    if /usr/local/bin/meshbridge-listener-ready; then
        log_info "meshtasticd TCP API is listening on internal port 4403"
        listener_description=$(/usr/local/bin/meshbridge-listener-ready --describe)
        log_info "meshtasticd TCP listener: ${listener_description}"
        listener_ready=1
        break
    fi
    sleep 1
    attempt=$((attempt + 1))
done

if [ "${listener_ready}" -ne 1 ]; then
    log_error "meshtasticd did not open internal TCP port 4403 within 30 seconds"
    stop_child
    exit 1
fi

if wait "${child_pid}"; then
    exit 0
else
    exit $?
fi
