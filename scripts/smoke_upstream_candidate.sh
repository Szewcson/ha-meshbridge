#!/bin/sh
# Validate changed immutable upstream daemon images before pinning or publishing.
set -eu

if [ "$#" -ne 2 ]; then
    echo "usage: $0 <candidates.json> <versions.json>" >&2
    exit 64
fi

candidates_file=$1
versions_file=$2
test_directory=$(mktemp -d)
results_file=$(mktemp)
container_names=""

cleanup() {
    for container_name in $container_names; do
        docker rm -f "$container_name" >/dev/null 2>&1 || true
    done
    rm -rf -- "$test_directory"
    rm -f -- "$results_file"
}
trap cleanup EXIT HUP INT TERM

changed_channels=$(jq -r '.channels | to_entries[] | select(.value.changed) | .key' "$candidates_file")
if [ -z "$changed_channels" ]; then
    printf '{}\n' > "$versions_file"
    exit 0
fi

for channel in $changed_channels; do
    case "$channel" in
        alpha|beta) ;;
        *)
            echo "candidate data contains an unsupported channel: $channel" >&2
            exit 1
            ;;
    esac
    image=$(jq -r --arg channel "$channel" '.channels[$channel].image' "$candidates_file")
    discovery_tag=$(jq -r --arg channel "$channel" '.channels[$channel].discovery_tag' "$candidates_file")
    digest=$(jq -r --arg channel "$channel" '.channels[$channel].digest' "$candidates_file")
    reference="${image}:${discovery_tag}@${digest}"
    container_name="meshbridge-upstream-${channel}-$$"
    channel_directory="${test_directory}/${channel}"
    mkdir -p "$channel_directory/state"
    printf 'General:\n  TCPPort: 4403\n' > "$channel_directory/runtime.yaml"

    docker pull "$reference" >/dev/null
    version=$(docker run --rm --entrypoint /usr/bin/meshtasticd "$reference" --version | tr -d '\r\n')
    if ! printf '%s\n' "$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9a-f]+$'; then
        echo "candidate $channel returned an invalid meshtasticd version: $version" >&2
        exit 1
    fi

    docker run -d --name "$container_name" \
        --entrypoint /usr/bin/meshtasticd \
        -v "$channel_directory":/candidate \
        "$reference" \
        --config /candidate/runtime.yaml --fsdir /candidate/state --sim >/dev/null
    container_names="$container_names $container_name"
    sleep 12
    status=$(docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' "$container_name")
    if [ "$status" != "running 0" ]; then
        docker logs "$container_name" >&2 || true
        echo "candidate $channel did not remain alive: $status" >&2
        exit 1
    fi
    if ! docker logs "$container_name" 2>&1 | grep -F 'API server listen on TCP port 4403' >/dev/null; then
        docker logs "$container_name" >&2 || true
        echo "candidate $channel did not start TCP port 4403" >&2
        exit 1
    fi
    if ! docker exec "$container_name" /bin/sh -c "awk 'NR > 1 && \$2 ~ /:1133$/ && \$4 == \"0A\" { found = 1 } END { exit !found }' /proc/net/tcp"; then
        echo "candidate $channel has no listening IPv4 TCP port 4403" >&2
        exit 1
    fi
    printf '%s\t%s\n' "$channel" "$version" >> "$results_file"
    docker rm -f "$container_name" >/dev/null
    container_names=$(printf '%s\n' "$container_names" | sed "s/ $container_name//")
done

jq -Rn '[inputs | split("\t") | {key: .[0], value: .[1]}] | from_entries' < "$results_file" > "$versions_file"
