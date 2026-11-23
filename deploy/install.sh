#!/usr/bin/env bash
# Install/update the arcade and its systemd service on the Raspberry Pi.
set -euo pipefail

APP_DIR="${APP_DIR:-/home/pi/led-arcade}"
VENV="${VENV:-/home/pi/neopixel-env}"
PYTHON="$VENV/bin/python"

if [ ! -f "$APP_DIR/app.py" ]; then
    echo "Arcade app not found at $APP_DIR/app.py" >&2
    exit 1
fi

if [ ! -x "$PYTHON" ]; then
    echo "Creating Python environment at $VENV"
    python3 -m venv --system-site-packages "$VENV"
fi

if ! command -v arecord >/dev/null 2>&1; then
    echo "Installing ALSA microphone utilities"
    apt-get update
    apt-get install -y alsa-utils
fi

if ! command -v mpg123 >/dev/null 2>&1; then
    echo "Installing mpg123 for song playback on the Pi speakers"
    # A failed package install must not block deploying the app itself.
    # Update errors from unrelated apt sources must not prevent installing from
    # the package lists that did load.
    apt-get update || echo "WARNING: apt-get update reported errors; trying the install anyway." >&2
    if ! apt-get install -y mpg123; then
        echo "WARNING: could not install mpg123; the song will not play on the Pi speakers." >&2
    fi
fi

# The on-board (headphone jack) audio driver uses the same PWM hardware as the
# LED strip on GPIO18; when it is active the strip freezes. Songs play through
# the USB audio interface, so keep the on-board driver off.
echo "Disabling on-board audio so it cannot take over the LED PWM"
for config in /boot/firmware/config.txt /boot/config.txt; do
    if [ -f "$config" ] && grep -q "^dtparam=audio=on" "$config"; then
        cp -n "$config" "$config.led-arcade.bak"
        sed -i 's/^dtparam=audio=on/dtparam=audio=off/' "$config"
        echo "Set dtparam=audio=off in $config (backup: $config.led-arcade.bak)"
    fi
done
echo "blacklist snd_bcm2835" > /etc/modprobe.d/led-arcade-no-onboard-audio.conf

echo "Installing Python requirements"
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -r "$APP_DIR/requirements.txt"

echo "Installing systemd service"
sed -e "s|/home/pi/led-arcade|$APP_DIR|g" \
    -e "s|/home/pi/neopixel-env|$VENV|g" \
    "$APP_DIR/deploy/led-arcade.service" \
    > /etc/systemd/system/led-arcade.service
chmod 0644 /etc/systemd/system/led-arcade.service
systemctl daemon-reload
systemctl enable led-arcade.service
systemctl restart led-arcade.service

echo "Arcade deployed. Check with: systemctl status led-arcade"
