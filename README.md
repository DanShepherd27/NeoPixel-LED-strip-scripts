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

The home screen also offers **Free music mode**. It listens to the Pi's
microphone input and expands/changes the LED pattern with ambient sound level;
clap transients flash the strip. It visualizes room sound and does not play or
stream music. The deploy script installs `alsa-utils` if `arecord` is missing.
To select a specific microphone, run `arecord -l` on the Pi and set
`LED_AUDIO_DEVICE` in `.deploy.env` (for example `plughw:1,0`) before deploying.
The home screen reports microphone status and capture errors while the mode is
active.

## MVP scope and roadmap

Included: central 40 FPS renderer, idle effects with automatic rotation,
global brightness and hidden end offsets, LAN web app, QR code, lobby,
dynamic player colors, and four games with results/rematch flow.

Still on the roadmap: smooth cross-fade transitions between idle effects;
configurable animation selection/duration from an admin UI; robust reconnect
and disconnect handling; richer game balance and real-world multiplayer
playtesting; Spotify music-reactive mode with a public queue link;
deployment validation on the target Pi and strip; and the broader additional
games, polish and security review described in `context.md`. Spotify remains
unimplemented.
