#!/usr/bin/env bash
# Install/update the arcade and its systemd service on the Raspberry Pi.
#
# Like `npm i`, a normal run only does what is missing or changed: packages whose
# commands exist are not reinstalled, services already enabled are not re-enabled, and
# pip runs only when requirements.txt changed. CLEAN=1 (deploy.py --clean) works like
# `npm ci`: it recreates the Python environment and runs every step.
set -euo pipefail

APP_DIR="${APP_DIR:-/home/pi/led-arcade}"
VENV="${VENV:-/home/pi/neopixel-env}"
CLEAN="${CLEAN:-0}"
PYTHON="$VENV/bin/python"
REQUIREMENTS_STAMP="$VENV/.led-arcade-requirements.sha256"

if [ ! -f "$APP_DIR/app.py" ]; then
    echo "Arcade app not found at $APP_DIR/app.py" >&2
    exit 1
fi

warn() { echo "WARNING: $*" >&2; }

is_clean() { [ "$CLEAN" = 1 ]; }

# True when the command is absent, or always for a clean install.
needs_command() { is_clean || ! command -v "$1" >/dev/null 2>&1; }

APT_UPDATED=0
apt_install() {
    if [ "$APT_UPDATED" = 0 ]; then
        APT_UPDATED=1
        # Update errors from unrelated apt sources must not prevent installing from
        # the package lists that did load.
        apt-get update || warn "apt-get update reported errors; trying the install anyway."
    fi
    apt-get install -y "$@"
}

# Copies SOURCE to DEST when the content differs; succeeds only if it copied.
install_if_changed() {
    if ! is_clean && cmp -s "$1" "$2"; then
        return 1
    fi
    install -m 0644 "$1" "$2"
}

# Enables and starts units, skipping the slow `enable` (bluetooth runs the SysV
# helper every time) when a unit is already enabled.
enable_and_start() {
    local unit
    for unit in "$@"; do
        if is_clean || ! systemctl is-enabled --quiet "$unit" 2>/dev/null; then
            systemctl enable "$unit"
        fi
        if ! systemctl is-active --quiet "$unit"; then
            systemctl start "$unit"
        fi
    done
}

if is_clean; then
    echo "Clean install: every step runs and the Python environment is rebuilt"
    if [ -f "$VENV/pyvenv.cfg" ]; then
        rm -rf "$VENV"
    fi
fi

if [ ! -x "$PYTHON" ]; then
    echo "Creating Python environment at $VENV"
    python3 -m venv --system-site-packages "$VENV"
fi

if needs_command arecord; then
    echo "Installing ALSA microphone utilities"
    apt_install alsa-utils
fi

if needs_command mpg123; then
    echo "Installing mpg123 for song playback on the Pi speakers"
    # A failed package install must not block deploying the app itself.
    apt_install mpg123 || warn "could not install mpg123; the song will not play on the Pi speakers."
fi

# The on-board (headphone jack) audio driver uses the same PWM hardware as the
# LED strip on GPIO18; when it is active the strip freezes. Songs play through
# the USB audio interface, so keep the on-board driver off.
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
if needs_command bluealsa-aplay || needs_command bt-agent; then
    echo "Installing Bluetooth audio receiver (BlueZ, bluez-alsa, bluez-tools)"
    apt_install bluez bluez-alsa-utils bluez-tools \
        || warn "could not install the Bluetooth packages; phones cannot stream to the Pi."
fi
if command -v bluealsa-aplay >/dev/null 2>&1 && command -v bt-agent >/dev/null 2>&1; then
    AGENT_UNIT=/etc/systemd/system/led-arcade-bt-agent.service
    AGENT_CHANGED=0
    if install_if_changed "$APP_DIR/deploy/led-arcade-bt-agent.service" "$AGENT_UNIT"; then
        echo "Installed the Bluetooth pairing agent service"
        AGENT_CHANGED=1
    fi
    # Earlier versions played phone audio from a separate service; the arcade app now owns it,
    # because BlueALSA allows only one reader of the stream.
    if [ -f /etc/systemd/system/led-arcade-bt-audio.service ]; then
        systemctl disable --now led-arcade-bt-audio.service 2>/dev/null || true
        rm -f /etc/systemd/system/led-arcade-bt-audio.service
        AGENT_CHANGED=1
    fi
    if [ "$AGENT_CHANGED" = 1 ]; then
        systemctl daemon-reload
    fi
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
    if needs_command rfkill; then
        apt_install rfkill || warn "could not install rfkill."
    fi
    rfkill unblock bluetooth || true
    enable_and_start bluetooth.service bluealsa.service
    # The package's own player would also grab every phone stream; ours targets the right output.
    if is_clean || systemctl is-enabled --quiet bluealsa-aplay.service 2>/dev/null; then
        systemctl disable --now bluealsa-aplay.service 2>/dev/null || true
    fi
    enable_and_start led-arcade-bt-agent.service
    if [ "$AGENT_CHANGED" = 1 ]; then
        systemctl restart led-arcade-bt-agent.service
    fi
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
        warn "$ASOUND_CONF is not managed by the arcade; leaving it alone."
    else
        if is_clean || ! dpkg -s libasound2-plugins >/dev/null 2>&1; then
            echo "Installing ALSA plugins for the software mixer"
            apt_install libasound2-plugins || warn "could not install libasound2-plugins."
        fi
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

# pip runs only when requirements.txt or the Python version changed since the last
# successful install into this environment.
REQUIREMENTS_HASH="$( { cat "$APP_DIR/requirements.txt"; "$PYTHON" --version; } | sha256sum | cut -d' ' -f1)"
if is_clean || [ "$(cat "$REQUIREMENTS_STAMP" 2>/dev/null)" != "$REQUIREMENTS_HASH" ]; then
    # rpi_ws281x compiles from source on newer Python versions and needs the headers.
    PYTHON_INCLUDE="$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_path("include"))')"
    if is_clean || [ ! -f "$PYTHON_INCLUDE/Python.h" ]; then
        echo "Installing Python headers to build rpi_ws281x"
        apt_install python3-dev build-essential
    fi
    echo "Installing Python requirements"
    "$PYTHON" -m pip install --upgrade pip
    "$PYTHON" -m pip install -r "$APP_DIR/requirements.txt"
    echo "$REQUIREMENTS_HASH" > "$REQUIREMENTS_STAMP"
else
    echo "Python requirements unchanged; skipping pip (deploy with --clean to reinstall)"
fi

SERVICE_UNIT=/etc/systemd/system/led-arcade.service
SERVICE_TEMP="$(mktemp)"
sed -e "s|/home/pi/led-arcade|$APP_DIR|g" \
    -e "s|/home/pi/neopixel-env|$VENV|g" \
    "$APP_DIR/deploy/led-arcade.service" > "$SERVICE_TEMP"
if install_if_changed "$SERVICE_TEMP" "$SERVICE_UNIT"; then
    echo "Installed systemd service"
    systemctl daemon-reload
fi
rm -f "$SERVICE_TEMP"
if is_clean || ! systemctl is-enabled --quiet led-arcade.service 2>/dev/null; then
    systemctl enable led-arcade.service
fi
systemctl restart led-arcade.service

echo "Arcade deployed. Check with: systemctl status led-arcade"
