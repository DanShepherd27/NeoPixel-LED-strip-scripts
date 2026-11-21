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
