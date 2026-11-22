# Raspberry Pi NeoPixel Arcade MVP

A LAN hosted, phone controlled LED arcade for a Raspberry Pi and a 60 LED
NeoPixel strip. The MVP has a continuous attract animation, a player lobby,
QR code joining, and four playable games: Reaction Race, Dodge, LED Battle,
and Strip Pong. Reaction Race supports one player, so the arcade can be tried
without a second phone.

## Configure

Edit `config.py` before launch:

- `LED_COUNT`: physical LEDs in the strip (default `60`)
- `LED_HIDDEN_START` / `LED_HIDDEN_END`: pixels to keep dark at each end
- `LED_ORIENTATION`: physical strip mounting (`"horizontal"` or `"vertical"`; currently `"vertical"`)
- `LED_BRIGHTNESS`: global brightness (`0`–`255`; default `40`)
- `HOST` / `PORT`: web server address (default `0.0.0.0:5000`)

The existing GPIO18, DMA, frequency, channel and `rpi_ws281x` setup is
preserved. Connect the strip's external power supply as required; do not power
the strip from the Pi's GPIO pin.

## Run locally without LED hardware

Python 3.10 or later is recommended. From the project directory:

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py --mock
```

Open `http://127.0.0.1:5000`. The `--mock` option runs the website and game
without attempting to drive physical LEDs. On Windows, `rpi_ws281x` may not
install; install the web dependencies (`Flask`, `Flask-SocketIO`, `qrcode`)
instead and run with `--mock`.

## Deploy on the Raspberry Pi

From the project folder, run the interactive deployment script:

```bash
python deploy/deploy.py
```

It prompts for the Pi hostname/IP and SSH username. If SSH key authentication
is not set up, OpenSSH prompts for the Pi login password during file copy and
installation. The default remote paths are `/home/<user>/led-arcade` and
`/home/<user>/neopixel-env`.

To save values between deployments, copy `.deploy.env.example` to
`.deploy.env` in the repository and edit it. The script reads the Pi address,
username, remote paths, and any `LED_ARCADE_*` secrets from that file. Missing
connection values are prompted; if the admin password is missing, it is
requested without echoing. `.deploy.env` is git-ignored and excluded from the
application archive. The `LED_ARCADE_*` values are copied over SSH into
`/etc/led-arcade.env` on the Pi with root-only permissions.

```powershell
Copy-Item .deploy.env.example .deploy.env
# Linux/macOS: cp .deploy.env.example .deploy.env
```

The script sends a clean project archive over SCP, creates the Python
environment if needed, installs dependencies, installs/enables the systemd
service and restarts it. It preserves `runtime-settings.json` on the Pi. The
configured Python environment should already contain the working
`rpi_ws281x` installation when possible; project requirements are installed
as part of deployment.

The service runs as root for GPIO access and restarts after failures. Check
deployment with:

```bash
sudo systemctl status led-arcade
sudo journalctl -u led-arcade -f
```

Open `http://<raspberry-pi-ip>:5000` from a phone on the same Wi-Fi. The
home screen includes a QR code. The **Admin settings** panel accepts that
password and lets you change the hidden LED count at both ends immediately;
values are persisted in `runtime-settings.json`. To run interactively on the
Pi instead of as a service, use:

```bash
sudo /home/pi/neopixel-env/bin/python /home/pi/led-arcade/app.py
```

The home screen also offers **Free music mode**. The default source is an
opted-in web user's microphone. The browser computes ambient volume and clap
features locally and sends only those values to the Pi; raw audio is not
recorded or transmitted. Users queue FIFO for exclusive microphone ownership,
and the admin can configure handoff duration. The Pi's ALSA microphone is used
as fallback. Browser microphone access requires trusted HTTPS; the default
`http://<pi-ip>:5000` address is not secure for phone browsers, so configure a
trusted HTTPS URL to use web microphones. The deploy script installs
`alsa-utils` if `arecord` is missing. To select a specific fallback microphone,
run `arecord -l` on the Pi and set
`LED_AUDIO_DEVICE` in `.deploy.env` (for example `plughw:1,0`) before deploying.
The home screen reports microphone source and capture errors while the mode is
active. Admin settings control the web microphone handoff interval (15 to
1800 seconds); it applies when other users are waiting. The music-mode card
offers six live-switchable patterns, including a retro VU meter with a mostly
green bar, yellow upper zone, and small red peak zone, plus shapes that move
inward from both ends. Admin settings also offer a
shared sensitivity slider (0.25x to 4x). Patterns stay saturated at high
levels, with a restrained magenta clap flash so loud sound does not wash the
strip into white.

If capture fails, compare the available devices with the configured device:

```bash
arecord -l
arecord -L
sudo arecord -D default -t raw -f S16_LE -c 1 -r 16000 -d 5 /tmp/mic-test.raw
```

If `default` cannot open the microphone, test the matching `plughw:CARD,DEVICE`
value shown by `arecord -l`, set that as `LED_AUDIO_DEVICE` in `.deploy.env`,
and redeploy. The service runs as root, so test capture with `sudo` too.

## MVP scope and roadmap

Included: central 40 FPS renderer, idle effects with automatic rotation,
global brightness and hidden end offsets, LAN web app, QR code, lobby,
dynamic player colors, and four games with results/rematch flow.

Still on the roadmap: white-backed QR code; tutorial review/replay followed
by an untimed ready gate; trusted HTTPS deployment for web microphones;
smooth cross-fades and admin animation controls;
robust reconnect handling; game balancing/playtesting; Spotify music-reactive
mode and public queue; Pi hardware validation; and the other games, polish,
and security review described in `context.md`. Spotify remains unimplemented.
