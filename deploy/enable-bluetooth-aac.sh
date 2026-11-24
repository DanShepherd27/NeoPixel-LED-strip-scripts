#!/usr/bin/env bash
# Optional: rebuild the bluealsa daemon with AAC so iPhones stream AAC instead of SBC.
# Debian ships bluez-alsa without AAC because libfdk-aac is non-free, so the daemon is
# built on the Pi from the same upstream version as the installed package and used through
# a systemd drop-in. Nothing is redistributed. Undo with:
#   sudo rm -r /etc/systemd/system/bluealsa.service.d && sudo systemctl daemon-reload \
#     && sudo systemctl restart bluealsa
# Run on the Pi as root: sudo bash enable-bluetooth-aac.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root: sudo bash $0" >&2
    exit 1
fi

VERSION="$(dpkg-query -W -f='${Version}' bluez-alsa-utils | sed -E 's/^([0-9.]+).*/\1/')"
if [ -z "$VERSION" ]; then
    echo "bluez-alsa-utils is not installed; run deploy/install.sh first." >&2
    exit 1
fi
echo "Building the bluealsa daemon $VERSION with AAC"

apt-get install -y build-essential autoconf automake libtool pkg-config \
    libasound2-dev libbluetooth-dev libdbus-1-dev libglib2.0-dev libsbc-dev libfdk-aac-dev

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
curl -fsSL "https://github.com/arkq/bluez-alsa/archive/refs/tags/v$VERSION.tar.gz" -o "$WORK/source.tar.gz"
tar -xzf "$WORK/source.tar.gz" -C "$WORK"

(
    cd "$WORK/bluez-alsa-$VERSION"
    autoreconf --install --force
    mkdir build
    cd build
    ../configure --enable-aac
    make -j"$(nproc)"
    # The daemon is "bluealsa" in 4.3 and "bluealsad" in later versions.
    for name in bluealsad bluealsa; do
        if [ -x "src/$name" ]; then
            install -m 0755 "src/$name" "/usr/local/bin/$name"
            echo "$name" > "$WORK/daemon-name"
            break
        fi
    done
    [ -s "$WORK/daemon-name" ] || { echo "The build produced no bluealsa daemon." >&2; exit 1; }
)
DAEMON="$(cat "$WORK/daemon-name")"

# Same command line as the packaged unit, with the AAC-enabled daemon binary.
EXEC_LINE="$(systemctl cat bluealsa.service | grep -m1 '^ExecStart=')"
NEW_EXEC="$(printf '%s\n' "$EXEC_LINE" | sed -E "s#^ExecStart=([-@:+!]*)[^ ]+#ExecStart=\1/usr/local/bin/$DAEMON#")"
if ! printf '%s\n' "$NEW_EXEC" | grep -q "/usr/local/bin/$DAEMON"; then
    echo "Could not adapt the bluealsa unit's ExecStart: $EXEC_LINE" >&2
    exit 1
fi
mkdir -p /etc/systemd/system/bluealsa.service.d
printf '[Service]\nExecStart=\n%s\n' "$NEW_EXEC" > /etc/systemd/system/bluealsa.service.d/aac.conf

systemctl daemon-reload
systemctl restart bluealsa.service led-arcade-bt-audio.service
echo "Done. Reconnect the phone, then check: bluealsa-cli list-pcms"
