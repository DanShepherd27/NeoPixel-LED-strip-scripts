# Agent Notes

## Project in one minute

This is a LAN-only Raspberry Pi arcade for a 60-pixel Adafruit WS2812/NeoPixel
strip. Phones join in a browser and control games; the Pi is the authoritative
game host and the only device that writes LED frames. Keep the app self-hosted
and usable without internet after installation.

## Hardware assumptions

- Raspberry Pi 4, Raspberry Pi OS; LED data is GPIO18 / physical pin 12.
- External power supplies the strip. Never power it from the Pi GPIO pin.
- Preserve the known-working `rpi_ws281x.PixelStrip` settings in `config.py`:
  count 60, 800 kHz, DMA 10, brightness 40, non-inverted, channel 0.
- The installed strip is vertical (`LED_ORIENTATION = "vertical"`).
- `LED_HIDDEN_START` and `LED_HIDDEN_END` are global counts of dark pixels at
  the physical ends. Admin changes apply immediately and persist in
  `runtime-settings.json` in the app directory.
- Free music mode reads microphone PCM from `arecord` via `led/audio.py`; the
  ALSA device is `LED_AUDIO_DEVICE` (default `default`). Capture runs only
  while the visualizer is active. It computes adaptive RMS volume and clap
  transients; the central renderer remains the sole LED writer.
- The systemd service runs as root because the current GPIO/DMA setup requires
  it. `/healthz` reports `led_hardware`, `led_error`, count and offsets. A
  `mock` value means the web process is alive but physical LED control failed;
  inspect `sudo journalctl -u led-arcade`.

## Architecture and where to change things

- `app.py`: loads persisted settings and starts one renderer and the web app.
- `led/hardware.py`: sole `rpi_ws281x` wrapper; only `led/renderer.py` writes
  frames to hardware. Do not call `strip.show()` from routes or games.
- `led/frame.py` and `led/effects/`: frame buffer and idle animations.
- `arcade/manager.py`: locked lifecycle/state owner and renderer scene.
- `arcade/games/`: one class per game, based on `BaseGame`. Games render into
  frames and never access hardware.
- `web/api.py`: HTTP controls plus the older Socket.IO event handlers;
  `web/routes.py`: pages, state, and health endpoints.
- Browser controls use local REST endpoints and poll `/api/state` every 500 ms.
  Do not reintroduce an assumed `/socket.io/socket.io.js` asset: Flask-SocketIO
  does not serve the browser client bundle, and the Pi must work offline.
- `templates/`, `static/js/`, `static/css/`: mobile browser UI. Static asset
  URLs use version query strings when necessary to bypass stale browser cache.

Lifecycle is `IDLE -> LOBBY -> TUTORIAL -> COUNTDOWN -> GAME -> RESULTS`.
Games define `tutorial_steps` and `render_tutorial(...)`; the manager
synchronizes tutorial time and pixels for all players. Each player can skip to
the countdown. Current games are Reaction Race, Dodge, Shooter/LED Battle,
and Pong.

## Network fairness status

The current client polls state every 500 ms and sends actions over HTTP. Games
run on the Pi's server clock; there is no clock synchronization, per-player
latency compensation, fixed input scheduling, or lag-aware pause yet. The
proposed fairness design is in `context.md` under “Fairness plan for network
delay”. Treat it as a plan, not implemented behavior. In particular, do not
claim Reaction Race scores are latency-corrected; the physical strip is the
shared cue, but button arrival time is currently scored on the server.

## Deploy and secrets

- From the repo, run `python deploy/deploy.py`. It prompts for the Pi address
  and SSH username; OpenSSH handles password prompts. `.deploy.env.example`
  can be copied to the git-ignored `.deploy.env` for saved connection values.
- Deployment archives exclude `.deploy.env` and local runtime settings. Only
  `LED_ARCADE_*` values are copied separately to `/etc/led-arcade.env` with
  root-only permissions.
- The site admin password is `LED_ARCADE_ADMIN_PASSWORD`. Do not commit
  `.deploy.env`, runtime settings, or credentials.
- `deploy/install.sh` creates the configured venv if missing, installs
  requirements, and installs/enables/restarts `led-arcade.service`.
- After a deploy, check `sudo systemctl status led-arcade`,
  `sudo journalctl -u led-arcade -n 100 --no-pager`, and
  `http://<pi-ip>:5000/healthz`.

## Current scope and deferred work

This is an MVP, not the full vision in `context.md`. Idle effects, lobby,
player colors, four games, pre-game tutorials, admin LED offsets, free
microphone music visualization, and basic deployment are present.
Cross-fades/admin animation controls, stronger
reconnect handling, game balancing/playtesting, more games, audio, and Pi
hardware validation remain. Spotify-reactive lighting and a public queue are
roadmap-only; do not implement them unless asked.

## Quick local checks

Use `python app.py --mock` for a no-hardware run (install web dependencies
first). Python compilation and `node --check static/js/app.js` are useful
quick syntax checks. Physical LED behavior must be verified on the Pi; use
`/healthz` and the systemd journal to distinguish app startup from hardware
initialization.
