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

# Bluetooth speaker: phones stream A2DP audio to the Pi's output. The admin's header
# button opens the pairing window; the agent below accepts pairing without a PIN.
if ! command -v bluealsa-aplay >/dev/null 2>&1 || ! command -v bt-agent >/dev/null 2>&1; then
    echo "Installing Bluetooth audio receiver (BlueZ, bluez-alsa, bluez-tools)"
    apt-get update || echo "WARNING: apt-get update reported errors; trying the install anyway." >&2
    if ! apt-get install -y bluez bluez-alsa-utils bluez-tools; then
        echo "WARNING: could not install the Bluetooth packages; phones cannot stream to the Pi." >&2
    fi
fi
if command -v bluealsa-aplay >/dev/null 2>&1 && command -v bt-agent >/dev/null 2>&1; then
    echo "Installing Bluetooth audio services"
    install -m 0644 "$APP_DIR/deploy/led-arcade-bt-agent.service" /etc/systemd/system/led-arcade-bt-agent.service
    # Earlier versions played phone audio from a separate service; the arcade app now owns it,
    # because BlueALSA allows only one reader of the stream.
    systemctl disable --now led-arcade-bt-audio.service 2>/dev/null || true
    rm -f /etc/systemd/system/led-arcade-bt-audio.service
    systemctl daemon-reload
    # iPhones only list devices that announce an audio device class; a stock Pi announces none.
    BLUETOOTH_CONF=/etc/bluetooth/main.conf
    if [ -f "$BLUETOOTH_CONF" ] && ! grep -q "^Class *= *0x200414" "$BLUETOOTH_CONF"; then
        cp -n "$BLUETOOTH_CONF" "$BLUETOOTH_CONF.led-arcade.bak"
        if grep -Eq "^#?Class *=" "$BLUETOOTH_CONF"; then
            sed -i -E "s/^#?Class *=.*/Class = 0x200414/" "$BLUETOOTH_CONF"
        else
            sed -i "/^\\[General\\]/a Class = 0x200414" "$BLUETOOTH_CONF"
        fi
        echo "Set the Bluetooth device class to audio speaker in $BLUETOOTH_CONF"
        systemctl restart bluetooth.service
    fi
    # The Lite image ships the radio soft-blocked and without the rfkill tool.
    command -v rfkill >/dev/null 2>&1 || apt-get install -y rfkill || echo "WARNING: could not install rfkill." >&2
    rfkill unblock bluetooth || true
    systemctl enable --now bluetooth.service bluealsa.service
    # The package's own player would also grab every phone stream; ours targets the right output.
    systemctl disable --now bluealsa-aplay.service 2>/dev/null || true
    systemctl enable led-arcade-bt-agent.service
    systemctl restart led-arcade-bt-agent.service
fi

# rpi_ws281x compiles from source on newer Python versions and needs the headers.
PYTHON_INCLUDE="$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_path("include"))')"
if [ ! -f "$PYTHON_INCLUDE/Python.h" ]; then
    echo "Installing Python headers to build rpi_ws281x"
    apt-get update || echo "WARNING: apt-get update reported errors; trying the install anyway." >&2
    apt-get install -y python3-dev build-essential
fi

# Optional software mixer (LED_DMIX_SLAVE in the arcade settings) so game sounds, songs and
# phone audio can play together. Output is then LED_OUTPUT_AUDIO_DEVICE=arcade_out.
read_setting() {
    [ -f /etc/led-arcade.env ] || return 0
    grep -m1 "^$1=" /etc/led-arcade.env | cut -d= -f2- | tr -d '"' || true
}
DMIX_SLAVE="$(read_setting LED_DMIX_SLAVE)"
if [ -n "$DMIX_SLAVE" ]; then
    ASOUND_CONF=/etc/asound.conf
    if [ -f "$ASOUND_CONF" ] && ! grep -q "Generated by led-arcade" "$ASOUND_CONF"; then
        echo "WARNING: $ASOUND_CONF is not managed by the arcade; leaving it alone." >&2
    else
        echo "Installing the ALSA software mixer for $DMIX_SLAVE"
        apt-get install -y libasound2-plugins || echo "WARNING: could not install libasound2-plugins." >&2
        RATE_CONVERTER=linear
        if ls /usr/lib/*/alsa-lib/libasound_module_rate_speexrate.so >/dev/null 2>&1; then
            RATE_CONVERTER=speexrate_medium
        fi
        bash "$APP_DIR/deploy/make-asound-conf.sh" "$DMIX_SLAVE" \
            "$(read_setting LED_DMIX_CHANNELS | grep . || echo 2)" \
            "$(read_setting LED_DMIX_RATE | grep . || echo 48000)" \
            "$RATE_CONVERTER" > "$ASOUND_CONF"
    fi
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
