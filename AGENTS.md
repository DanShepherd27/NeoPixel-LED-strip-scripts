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
- Sound-reactive lighting offers eleven live-switchable browser patterns, prefers
  an opted-in browser microphone and falls back to
  microphone PCM from `arecord` via `led/audio.py`; the ALSA device is
  `LED_AUDIO_DEVICE` (default `default`). Browser audio stays local; only
  normalized volume/peak/clap and six frequency-band values are sent. One
  browser owns the mic at a time, with
  a FIFO queue and admin-configured handoff (`mic_handoff_seconds` in runtime
  settings). Browser mic requires trusted HTTPS on phones; the default LAN
  HTTP address falls back to ALSA. The central renderer remains the sole LED
  writer. Admin settings select the persisted startup pattern and adjust
  shared visualizer sensitivity from 0.25x to 4x. The sound-reactive UI shows
  the color controls supported by each pattern; the six-band spectrum has six
  independent pickers. Admin Save Settings persists palettes. Red Pulse uses
  only the red LED channel. The pattern selector changes the active
  pattern and colors immediately. Retro VU maps green, yellow, and red VU zones
  to the vertical strip, with a cyan peak marker that holds 500 ms before
  falling. Its playful RMS curve has an 8-10 LED floor; sample peaks only boost
  it when RMS confirms sound, preventing room noise from pinning the meter.
  The six-band spectrum uses six coarse frequency bands; these represent
  ranges and do not isolate individual instruments. Sound-reactive checkboxes select
  the bands that render. The strip preview uses the renderer's last 60-pixel
  frame, including peak/beat flashes, with hardware offsets and RGB balance
  applied; it is horizontal in landscape and vertical in portrait. The six-band
  spectrum keeps its frequency colors confined to their bands.
  Sound-reactive lighting estimates BPM from bass-band onsets, adds a predicted beat pulse
  to every pattern, and compensates with measured mic/network latency. Admin
  beat-sync timing adds a saved -100 to +200 ms manual trim.
  Keep colors saturated at high levels; the clap flash should not wash the
  strip white.
- The Pi's on-board audio driver (`snd_bcm2835`) shares the PWM hardware with the
  LED data pin, and when active the strip freezes on one frame while `/healthz`
  still says `ready`. `deploy/install.sh` sets `dtparam=audio=off`, blacklists the
  module, and the service unloads it in `ExecStartPre`. Songs use the USB audio
  interface, so this costs nothing.
- Bluetooth speaker: `deploy/install.sh` installs BlueZ, bluez-alsa and bluez-tools, and two
  units (`led-arcade-bt-agent` accepts PIN-less pairing; `led-arcade-bt-audio` plays A2DP
  on `LED_OUTPUT_AUDIO_DEVICE`). The admin-only header button
  (`POST /api/admin/bluetooth/discoverable`, `web/bluetooth.py`) disconnects and unpairs
  whoever is connected, then makes the Pi discoverable for
  `LED_BLUETOOTH_DISCOVERABLE_SECONDS` (default 120).
- The systemd service runs as root because the current GPIO/DMA setup requires
  it. `/healthz` reports `led_hardware`, `led_error`, count and offsets. A
  `mock` value means the web process is alive but physical LED control failed;
  inspect `sudo journalctl -u led-arcade`.

## Song light show

Every song is a `*.ledcue.json` show file in `assets/song/` (format and
rationale in `docs/show-format.md`): cues launch named patterns at song
timecodes (seconds or `bar|beat|tick` through a tempo map), so latency and seeking
only change the clock, never the file. `cuesheet.py` compiles a show once;
`engine.py` plays it (tracks, cross-fades, tracking-style `seek`); `patterns.py`
maps pattern names to `moods.py` (calm) and `peaks.py` (build/chorus/bridge/finale)
classes, which draw on the beat envelopes in `rhythm.py`; `library.py` lists
songs. `tools/analyze_song.py` (offline, needs numpy) writes the analysis JSON
the show references: 40 Hz loudness/band features plus a beat-tracked tempo
(this song: 150.147 BPM, first beat 0.012 s, beat 0 = downbeat, snare on beats
2/4). A constant-tempo guess 0.2% off drifts half a second over the song, so
re-run the tool and update the show's `tempo_map` if the MP3 changes.
`tools/compile_show.py` builds a show from a DAW-authored MIDI file. Admin "Add a song"
uploads an MP3 to `LED_SONG_DIR` (default `user-songs/`, git-ignored and never
deployed over): `importer.py` runs `analyzer.py` (numpy; mpg123/ffmpeg decode) and
`showgen.py` in a niced subprocess, one job at a time, and the song appears for
everyone when ready (`song_imports` in `/api/state`). `showgen.py` is stdlib-only and
plans dance tracks from kick presence: intro, breakdown, build, drop, outro; the
tempo grid is the comb fold in `track_beats`, shifted to the kick if the off-beat hats
dominate. Non-dance music gets one long "drop" with alternating palettes. Two looks: "club" (red, black and white only; `techno.py` gives each sound one fixed visual for the whole song: kick = a wave from the centre paced to reach the ends on the next beat, snare = end blocks on beats 2/4, acid/lead = bar height from the 300 Hz-5 kHz bands, phrase start = the only full-strip flash, phrase fill = rounds from both ends; no randomness; layers on the base/fx/flash/lead tracks) and "neon". Keep large-area flashes (a quarter of the strip brightening by 30% in one frame) at or below 3 per second in every show: tests check the patterns of the Christmas show and both generated looks, and `engine.FlashGuard` holds back any fourth flash in a second as a safety net. Moves that land on a beat must happen in the same frame as the beat's pop (`stepped` is instant by default) so they read as one flash. Run
`python -m unittest discover tests` after touching any of this.

`SongSession` owns the clock and Pi playback (`mpg123`; `LED_OUTPUT_AUDIO_DEVICE`,
default `LED_AUDIO_DEVICE`, selects the ALSA output, e.g.
`plughw:CARD=U192k,DEV=0`). The lights are shifted by the speaker latency
(`song_audio_latency_ms` in runtime settings, env default
`LED_SONG_AUDIO_LATENCY_MS`). `arcade/song/latency.py` measures it with the Pi's
own microphone: it cross-correlates the mic loudness (`AudioInput.history_since`)
with the song's known loudness. Admin "Measure with speaker + mic" plays the
first 18 s and saves the result; with auto-sync on, the same estimator runs
every 3 s during playback and nudges latency (max 30 ms/step, +-300 ms) and
saves it when the song ends. Estimation runs in a background thread so the
renderer never stalls. Transport (`POST /api/song/control`: pause/resume/seek, UI in
`static/js/song-transport.js`) restarts the Pi player at the chosen MP3 frame
(`mpg123 -k`; other players use their start-offset flag), resets the
choreography and the latency tracker, and holds a dimmed frame while paused.
Browsers can also stream `/api/song/audio`
(range-capable); `static/js/song.js` keeps it within 0.25 s of the server position.

## Architecture and where to change things

- `app.py`: loads persisted settings and starts one renderer and the web app.
- Games, the lobby and results draw only on the LEDs the admin left visible:
  `ArcadeManager._render_in_play_area` hands them a shorter frame and games use
  `manager.play_count`, never `manager.count`.
- `arcade/sounds.py`: retro square-wave effects synthesized at start-up and played
  with `aplay` on `LED_OUTPUT_AUDIO_DEVICE`; call `manager.sound(name)`. Set
  `LED_ARCADE_GAME_SOUNDS=0` to mute.
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
The players taking part (first to join, up to the game's `max_players`) must
mark ready before the tutorial starts, unless only one person is playing: solo
play skips both ready checks. Extra players queue first come first served, see
their position, cannot steer or advance the demo, and get the next game
(`_finish_results` moves the players to the back of the queue). Silent phones
(no input/heartbeat for 20 s) count as away and are dropped after 120 s. Any
player can vote to kick another; a majority of the other connected players
removes them and their device cannot rejoin for two minutes. The tutorial has one primary button: Next through the steps, then Ready (Start when
playing alone); finishing the last step marks that player ready. Games
define `tutorial_steps` and `render_tutorial(...)`; each step's demo loops until a
participant presses Next, then (for several players) the game waits without a
timer until all mark ready; players can replay the demo, which resets
readiness. The browser controller is built once per game; never rebuild it on a
state poll, or held buttons lose their pointerup. Current games are Reaction Race, Dodge,
Shooter/LED Battle, and Pong. Pong takes 1-2 players; a lone player faces the
machine (`PongGame.MACHINE_ID`, right end). It plans one swing per ball sent its
way (at least `MACHINE_MIN_REACTION` after the hit, aimed at the zone's middle with
`MACHINE_TIMING_ERROR` seconds of jitter), so it misses more as the ball speeds up
and the zone's time window shrinks.
Pong is played in three levels: each end's hit zone is lit in its guard's player
color (the machine is cyan), a level is first to 3 points, and the match goes to
whoever wins 2 levels. Every hit speeds the ball up (longer trail, higher beep);
each level starts faster, and between levels the game waits until every connected
human presses "Start level" on their phone (`next_level` input). A machine win has no player record, so the game supplies `results["winner_name"]`
and `results["winner_color"]` for the results screen.

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

## Commits and authorship

- Commits are authored only by the repository owner. Agents must not add
  themselves as an author or co-author: no `Co-Authored-By:` trailer naming
  Claude or any other AI, and no "Generated with" lines in commit messages.
- Commit messages describe the change in plain words; end them without any
  attribution line.

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
