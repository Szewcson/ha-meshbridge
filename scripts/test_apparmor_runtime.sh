#!/bin/sh
# Exercise an App image under its exact custom AppArmor profile. There is no
# USB device in CI, so the wrapper must safely reject either no matching device
# or a descriptor that sysfs exposes without mapping into the container. The
# official daemon then runs only in its built-in simulator to prove the
# contained listener path without accessing a radio.
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: $0 <app-directory>" >&2
    exit 64
fi

app_directory=$1
profile_path="$app_directory/apparmor.txt"
slug=$(awk '/^slug:/ { print $2; exit }' "$app_directory/config.yaml")
if [ -z "$slug" ] || [ ! -f "$profile_path" ]; then
    echo "invalid App directory: $app_directory" >&2
    exit 64
fi

test_directory=$(mktemp -d)
run_log=$(mktemp)
sim_log=$(mktemp)
container_name="ha-${slug}-apparmor-smoke-$$"
sim_container_name="${container_name}-sim"
image_name="ha-${slug}-apparmor-smoke:current"
profile_loaded=false

cleanup() {
    sudo -n docker rm -f "$container_name" >/dev/null 2>&1 || true
    sudo -n docker rm -f "$sim_container_name" >/dev/null 2>&1 || true
    if [ "$profile_loaded" = true ]; then
        sudo -n /usr/sbin/apparmor_parser -R "$profile_path" >/dev/null 2>&1 || true
    fi
    sudo -n rm -rf -- "$test_directory"
    rm -f -- "$run_log"
    rm -f -- "$sim_log"
}
trap cleanup EXIT HUP INT TERM

printf '%s\n' \
    '{"usb_selector":"serial","usb_serial":"apparmor-smoke","log_level":"info","hardware":{"mode":"custom","config":"Meta:\n  name: apparmor-smoke\nLora:\n  Module: sx1262\n  USB_VID: 0x1A86\n  USB_PID: 0x1234\n  USB_Serialnum: apparmor-smoke\n"}}' \
    > "$test_directory/options.json"

# Match Supervisor-owned App data permissions before first state creation.
sudo -n chown root:root "$test_directory" "$test_directory/options.json"
sudo -n chmod 700 "$test_directory"

audit_baseline=$(sudo -n dmesg --color=never | wc -l)
sudo -n /usr/sbin/apparmor_parser -r "$profile_path"
profile_loaded=true

sudo -n docker build --pull -q -t "$image_name" "$app_directory"
set +e
sudo -n docker run --name "$container_name" --security-opt "apparmor=$slug" \
    -v "$test_directory":/data "$image_name" > "$run_log" 2>&1
runtime_status=$?
set -e

cat "$run_log"
if [ "$runtime_status" -ne 1 ]; then
    echo "expected safe no-USB startup refusal (exit 1), got $runtime_status" >&2
    exit 1
fi
if ! grep -E "Startup validation failed: (expected exactly one USB device with serial 'apparmor-smoke'; found 0|cannot read USB serial descriptor:)" \
    "$run_log" >/dev/null; then
    echo "launcher did not safely reject the unavailable CI USB device" >&2
    exit 1
fi
if ! sudo -n test -s "$test_directory/app-state.json"; then
    echo "launcher did not atomically create persistent App state" >&2
    exit 1
fi

sudo -n docker run -d --name "$sim_container_name" --security-opt "apparmor=$slug" \
    --entrypoint /usr/bin/meshtasticd -v "$test_directory":/data "$image_name" \
    --config /data/generated/current/runtime.yaml --fsdir /data/meshbridge-state --sim \
    > /dev/null
sleep 12
sim_status=$(sudo -n docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' "$sim_container_name")
sudo -n docker logs "$sim_container_name" > "$sim_log" 2>&1
cat "$sim_log"
if [ "$sim_status" != "running 0" ]; then
    echo "simulated daemon did not remain running: $sim_status" >&2
    exit 1
fi
if ! grep -F "API server listen on TCP port 4403" "$sim_log" >/dev/null; then
    echo "simulated daemon did not open its internal TCP API" >&2
    exit 1
fi
listener_description=$(sudo -n docker exec "$sim_container_name" /usr/local/bin/meshbridge-listener-ready --describe)
if ! printf '%s\n' "$listener_description" | grep -Fx "IPv4 0.0.0.0:4403" >/dev/null; then
    printf '%s\n' "$listener_description" >&2
    echo "simulated daemon did not bind the internal TCP API to all IPv4 interfaces" >&2
    exit 1
fi

# Docker represents the inherited HEALTHCHECK NONE sentinel as non-empty image
# metadata. Supervisor mistakes that sentinel for a real check and leaves the
# App in startup forever. The replacement check must become healthy while the
# exact AppArmor profile is active.
health_status=""
health_attempt=0
while [ "$health_attempt" -lt 9 ]; do
    health_status=$(sudo -n docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$sim_container_name")
    if [ "$health_status" = "healthy" ]; then
        break
    fi
    sleep 5
    health_attempt=$((health_attempt + 1))
done
if [ "$health_status" != "healthy" ]; then
    sudo -n docker inspect --format '{{json .State.Health}}' "$sim_container_name" >&2
    echo "listener health check did not become healthy under AppArmor: ${health_status:-missing}" >&2
    exit 1
fi
sudo -n docker rm -f "$sim_container_name" >/dev/null

new_denials=$(sudo -n dmesg --color=never | tail -n "+$((audit_baseline + 1))" \
    | grep "apparmor=\"DENIED\".*profile=\"$slug\"" || true)
unexpected_denials=$(printf '%s\n' "$new_denials" \
    | grep -v "profile=\"$slug\".*family=\"bluetooth\".*sock_type=\"raw\"" || true)
if [ -n "$unexpected_denials" ]; then
    printf '%s\n' "$unexpected_denials" >&2
    echo "AppArmor denied an unexpected startup path" >&2
    exit 1
fi

if [ -n "$new_denials" ]; then
    echo "Observed the documented, blocked native Bluetooth probe"
fi

echo "AppArmor runtime smoke test passed for $slug with no unexpected denials"
