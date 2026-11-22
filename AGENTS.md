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
- Roadmap UI requirement: give the QR code a white background/quiet zone while
  retaining the dark theme everywhere else.
- `LED_HIDDEN_START` and `LED_HIDDEN_END` are global counts of dark pixels at
  the physical ends. Admin changes apply immediately and persist in
  `runtime-settings.json` in the app directory.
- Admin LED color balance (`led_color_red/green/blue`) scales each RGB output
  channel globally from 0–200%, applies to all scenes, and persists beside the
  other runtime settings. Defaults are 100% per channel.
- Free music mode offers eight live-switchable browser UI patterns (center pulse,
  mirror bars, rainbow wave, comet, retro VU meter, live band spectrum, inward
  diamonds, red shades), prefers
  an opted-in browser microphone and falls back to
  microphone PCM from `arecord` via `led/audio.py`; the ALSA device is
  `LED_AUDIO_DEVICE` (default `default`). Browser audio stays local; only
  normalized volume/peak/clap and six frequency-band values are sent. One
  browser owns the mic at a time, with
  a FIFO queue and admin-configured handoff (`mic_handoff_seconds` in runtime
  settings). Browser mic requires trusted HTTPS on phones; the default LAN
  HTTP address falls back to ALSA. The central renderer remains the sole LED
  writer. Admin settings select the persisted startup pattern and adjust
  shared visualizer sensitivity from 0.25x to 4x. The music-mode UI also has
  primary/accent color pickers; Admin Save Settings persists them. Red Shades
  uses only the red LED channel. The music-mode selector changes the active
  pattern and colors immediately. Retro VU maps green, yellow, and red VU zones
  to the vertical strip, with a cyan peak marker that holds 500 ms before
  falling. Its playful RMS curve has an 8-10 LED floor; sample peaks only boost
  it when RMS confirms sound, preventing room noise from pinning the meter.
  The Live Band Spectrum uses six coarse frequency bands; these represent
  ranges and do not isolate individual instruments. Music UI checkboxes select
  the bands that render. The strip preview uses the renderer's last 60-pixel
  frame, including peak/beat flashes, with hardware offsets and RGB balance
  applied; it is horizontal in landscape and vertical in portrait. Live Band
  Spectrum keeps its frequency colors confined to their bands.
  Music mode estimates BPM from bass-band onsets, adds a predicted beat pulse
  to every pattern, and compensates with measured mic/network latency. Admin
  beat-sync timing adds a saved -100 to +200 ms manual trim.
  Keep colors saturated at high levels; the clap flash should not wash the
  strip white.
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
- `web/api.py`: local HTTP controls; `web/admin.py`: authenticated persisted
  settings; `web/music_api.py`: music and microphone routes;
  `web/socket_api.py`: older Socket.IO handlers. `web/routes.py` owns pages,
  state, and health endpoints.
- Browser controls use local REST endpoints and poll `/api/state` every 500 ms.
  Do not reintroduce an assumed `/socket.io/socket.io.js` asset: Flask-SocketIO
  does not serve the browser client bundle, and the Pi must work offline.
- `templates/`, `static/js/`, `static/css/`: mobile browser UI. Static asset
  URLs use version query strings when necessary to bypass stale browser cache.

## Coding style

- Prefer clear, direct code and single-purpose functions or modules. Keep each
  module focused on one responsibility and use SOLID principles where they
  improve separation without adding unnecessary abstraction.
- Treat files over 200 lines as a prompt to review their responsibilities and
  consider a focused extraction. This is a review signal, not a strict limit;
  keep cohesive code together when splitting would make dependencies harder to
  follow.
- In JavaScript, use `const` by default and `let` only for bindings that are
  reassigned. Do not introduce `var`. Keep browser code compatible with current
  mobile browsers and usable offline; avoid adding runtime dependencies without
  a clear need.
- In Python, follow the surrounding style and standard library conventions.
  Keep hardware access behind `led/hardware.py` and preserve the renderer as
  the sole LED frame writer.
- Prefer existing project helpers and dependencies over duplicate utilities or
  new packages. Name values and functions for their purpose, and remove stale
  comments or documentation when behavior changes.

Lifecycle currently is `IDLE -> LOBBY -> TUTORIAL -> COUNTDOWN -> GAME -> RESULTS`.
Every connected lobby player must mark ready before the tutorial starts. Games
define `tutorial_steps` and `render_tutorial(...)`; the manager synchronizes
tutorial time and pixels for all players. After the demo, the game waits
without a timer until every connected player marks ready; players can replay
the demo, which resets readiness. Current games are Reaction Race, Dodge,
Shooter/LED Battle, and Pong.

For new work, first look for a plug-and-play library, existing browser API, or
reusable building block already in the repo/environment. Avoid custom code or
new dependencies when an existing solution fits the offline Raspberry Pi.

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
- Deployment archives exclude `.deploy.env` and local runtime settings.
  `LED_ARCADE_*` and `LED_AUDIO_*` values are copied separately to
  `/etc/led-arcade.env` with root-only permissions.
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
browser-first microphone music visualization with a FIFO lease, and basic
deployment are present.
Cross-fades/admin animation controls, stronger reconnect handling, game
balancing/playtesting, more games, trusted HTTPS for phone microphone access,
white-backed QR, and Pi hardware validation remain. Spotify-reactive lighting
and a public queue are roadmap-only; do not implement them unless asked.

## Quick local checks

Use `python app.py --mock` for a no-hardware run (install web dependencies
first). Python compilation and `node --check static/js/app.js` are useful
quick syntax checks. Physical LED behavior must be verified on the Pi; use
`/healthz` and the systemd journal to distinguish app startup from hardware
initialization.
