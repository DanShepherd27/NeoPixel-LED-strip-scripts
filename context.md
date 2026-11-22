# Raspberry Pi NeoPixel Arcade — Project Context & Development Brief

## 1. Project Overview

Build a small multiplayer arcade powered by a Raspberry Pi 4 Model B and a 60-LED RGB NeoPixel strip.

The Raspberry Pi should act as both:

- The LED controller
- A local web server hosting a mobile-friendly multiplayer arcade

People connected to the same Wi-Fi/LAN should be able to open the website on their phones, join games, and interact with the physical LED strip in real time.

The project should feel like a fun physical arcade installation, particularly suitable for parties, gatherings, Christmas, and casual multiplayer gaming.

The system should work independently without requiring a monitor, keyboard, mouse, or internet connection once installed.

---

## 2. Hardware

### Raspberry Pi

- Raspberry Pi 4 Model B
- Raspberry Pi OS
- Accessible over SSH
- Hostname currently: `raspberrypi`
- LAN access
- Headless operation is preferred

### LED strip

- Adafruit NeoPixel RGB LED strip
- Product: https://www.adafruit.com/product/1461
- 60 LEDs
- WS2812/NeoPixel-compatible
- Single-dimensional physical display (1D LED strip)

### GPIO

- GPIO18
- Physical pin 12
- LED data signal

The strip uses an external power supply. Raspberry Pi GPIO should only provide the data signal.

### Software/hardware library

The following library has already been installed and tested successfully:

```python
from rpi_ws281x import PixelStrip, Color
```

Current known-working configuration:

```python
LED_COUNT = 60
LED_HIDDEN_START = 0  # physical LEDs hidden at the beginning of the strip
LED_HIDDEN_END = 0    # physical LEDs hidden at the end of the strip
LED_PIN = 18
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 40
LED_INVERT = False
LED_CHANNEL = 0
```

Example initialization:

```python
strip = PixelStrip(
    LED_COUNT,
    LED_PIN,
    LED_FREQ_HZ,
    LED_DMA,
    LED_INVERT,
    LED_BRIGHTNESS,
    LED_CHANNEL
)

strip.begin()
```

The LEDs have already been successfully controlled using Python on this Raspberry Pi.

### Python environment

Existing virtual environment:

```text
/home/pi/neopixel-env
```

Python executable:

```text
/home/pi/neopixel-env/bin/python
```

The working NeoPixel library is:

```text
rpi_ws281x
```

Run the LED application with elevated permissions, as required by the current GPIO configuration:

```bash
sudo /home/pi/neopixel-env/bin/python /home/pi/led_game.py
```

Do not unnecessarily replace the currently working LED control library or GPIO configuration.

---

## 3. Current Prototype

There is currently a Python Flask application at:

```text
/home/pi/led_game.py
```

It hosts a website on port 5000.

The web server can be accessed from other devices on the LAN using:

```text
http://<RASPBERRY_PI_IP>:5000
```

The application has already been tested successfully from another device after correcting an initially incorrect IP address.

The current prototype has basic functionality:

- Flask web server
- Browser-based player joining
- Basic player list
- Basic color assignment
- A simple territory-capture game
- Web requests controlling the physical LEDs

However, it is only a proof-of-concept and should not be considered the final architecture.

### Current shortcomings

- LEDs go dark when nobody is playing
- No proper idle/attract animation system
- No game selection system
- Only one basic game
- Gameplay is not sufficiently fun or animated
- Current game logic is simplistic
- Player limit is hard-coded to three
- Color assignment is limited to red, green and blue
- LED rendering and game logic are tightly coupled
- No proper arcade-style lifecycle
- No polished mobile UI
- No lobby/game/result state flow

The objective is to significantly improve or replace the current prototype.

Before changing the code, inspect the existing files and preserve the currently working hardware configuration.

---

# 4. Product Vision

Transform the Raspberry Pi into a **local multiplayer LED arcade**.

The LED strip should always be doing something visually interesting.

When nobody is playing:

- The strip continuously displays ambient animations
- The system acts as an attractive LED installation
- The website displays an arcade/attract screen
- Visitors can join or start a game

When people play:

- Their phones act as controllers
- The physical LED strip becomes the game display
- Players see the game state on their phones
- Gameplay actions immediately affect the LEDs
- Games support multiple players where appropriate

When a game ends:

- Display a victory/result animation
- Show scores and winner
- Offer rematch or return to arcade
- Return to idle mode when nobody starts another game

The experience should be playful, visually satisfying, responsive and intuitive without requiring instructions from the developer.

---

# 5. Core Architecture

The application should use a modular architecture rather than one large Flask script.

Suggested structure:

```text
led-arcade/
│
├── app.py
├── config.py
├── requirements.txt
│
├── led/
│   ├── hardware.py
│   ├── renderer.py
│   ├── frame.py
│   └── effects/
│       ├── rainbow.py
│       ├── comet.py
│       ├── fire.py
│       ├── twinkle.py
│       ├── particles.py
│       └── color_wave.py
│
├── arcade/
│   ├── manager.py
│   ├── state.py
│   ├── players.py
│   ├── colors.py
│   └── games/
│       ├── base.py
│       ├── shooter.py
│       ├── dodge.py
│       ├── reaction.py
│       └── pong.py
│
├── web/
│   ├── routes.py
│   ├── api.py
│   └── templates/
│       └── index.html
│
└── static/
    ├── css/
    │   └── arcade.css
    └── js/
        ├── app.js
        ├── controller.js
        └── games.js
```

This is a suggested structure, not a rigid requirement. Keep the architecture appropriately simple for a Raspberry Pi project.

Do not over-engineer it with unnecessary microservices, databases, Docker, cloud services or complicated deployment infrastructure.

---

## 6. LED Rendering Architecture

### Critical requirement: one LED rendering loop

Only one component should control and write frames to the physical LED strip.

Do not allow Flask routes, game threads, animation threads and game-specific code to independently call `strip.show()`.

Use a central renderer.

Conceptual architecture:

```text
Mobile browsers
      │
      ▼
Web server
      │
      ▼
Player input / API
      │
      ▼
Arcade manager
      │
      ├── Idle animation
      ├── Lobby animation
      ├── Game 1
      ├── Game 2
      ├── Game 3
      └── Game 4
      │
      ▼
Frame renderer
      │
      ▼
60 RGB pixels
      │
      ▼
NeoPixel hardware
```

The renderer should continuously generate frames at a suitable frame rate, ideally around 30–50 FPS, subject to performance and hardware constraints.

Each animation or game should produce an RGB frame of 60 pixels.

A conceptual frame:

```python
frame = [
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    ...
]
```

The renderer translates the frame into NeoPixel output.

### Rendering rules

- Centralize LED writes
- Keep game logic separate from hardware code
- Avoid race conditions
- Avoid flickering from conflicting LED updates
- Keep animations smooth
- Use frame-based updates
- Games should be able to use the full strip
- Effects should be composable when practical
- Use low brightness by default
- Support global brightness configuration

The renderer should have a clear state hierarchy:

```text
ARCADE
│
├── IDLE
│   └── Ambient animation
│
├── LOBBY
│   └── Lobby animation
│
├── GAME
│   └── Active game rendering
│
├── RESULTS
│   └── Winner animation
│
└── TRANSITION
    └── Transition effects
```

The system should never unnecessarily turn the LEDs off.

---

# 7. Idle / Attract Mode

This is a very important feature.

Whenever there is no active game, the LEDs should continuously run visually appealing animations.

Idle mode should be dynamic and should not just display a static pattern.

### Desired animations

Implement a collection of effects that can run independently or be combined:

#### Rainbow wave

A continuously moving rainbow across the strip.

#### Comet

A bright head moving along the strip with a fading tail.

#### Bouncing particles

Several colored particles move along the strip and bounce at the ends.

#### Fire / embers

An animated heat simulation using reds, oranges and yellows.

#### Twinkling stars

Random pixels illuminate and fade smoothly.

#### Christmas mode

Red, green, gold and warm white lights, with patterns such as:

- Alternating colors
- Twinkling
- Candy-cane patterns
- Random sparkle
- Slow pulses
- Comets

#### Color breathing

A smooth color intensity pulse.

#### Color waves

Multiple colors move along the strip in waves.

#### Random sparkle

Random LEDs illuminate briefly, then fade.

#### Color wipe

Colors progressively fill or travel across the strip.

### Idle animation behavior

- Automatically switch between animations
- Transitions should be smooth when possible
- Animation durations should be configurable
- Avoid abrupt black frames
- Avoid turning the LEDs off between effects
- Idle should run indefinitely
- Consider an automatic playlist/random selection
- The website should display the current idle animation name
- The administrator should be able to select or skip an idle effect

Suggested idle behavior:

```text
Rainbow Wave
    ↓
Comet
    ↓
Twinkle
    ↓
Fire
    ↓
Christmas Sparkle
    ↓
Color Wave
    ↓
Randomly selected next animation
```

The idle mode is also the arcade's attract mode.

---

# 8. Player Management

## Unlimited players

Remove the hard-coded player limit.

The system should allow as many players to join as is reasonably practical for the application.

Players should have:

- Unique player ID
- Nickname
- Assigned color
- Connection status
- Score
- Game-specific state
- Optional ready status

Players should be able to join through the web interface.

The application should support players joining the lobby before a game starts.

Game-specific restrictions are allowed. For example, Pong might have exactly two players, while reaction games or shooters may support many players.

Do not impose a global hard-coded limit of three players.

---

# 9. Player Color Assignment

Player colors should be assigned dynamically and should not be limited to RGB primary colors.

Colors should be distributed evenly around the hue/color wheel.

Use HSV/HSL or another suitable color-space representation.

For N players, distribute hue approximately as:

```text
Hue(i) = (360° × i) / N
```

Examples:

| Players | Hue distribution                           |
| ------- | ------------------------------------------ |
| 2       | 0°, 180°                                   |
| 3       | 0°, 120°, 240°                             |
| 4       | 0°, 90°, 180°, 270°                        |
| 5       | 0°, 72°, 144°, 216°, 288°                  |
| 8       | 0°, 45°, 90°, 135°, 180°, 225°, 270°, 315° |

Convert the hues into RGB values for LED display and the web UI.

### Color assignment behavior

- Colors should be visually distinct
- Colors should be evenly distributed around the wheel
- Player colors should be recalculated as players join/leave the lobby if appropriate
- Once the game begins, player colors should be locked for the duration of the game
- Do not change colors during an active game
- Avoid assigning identical colors
- Consider brightness/saturation constraints for visibility
- If many players join, preserve hue separation as much as mathematically possible

The website should clearly display each player's assigned color.

---

# 10. Multiplayer Game Framework

Implement games as separate modules that share a common interface.

Each game should support, as applicable:

```text
initialize()
start()
update(delta_time)
handle_input(player_id, input)
render()
end()
get_state()
```

The arcade manager should:

- Handle game selection
- Manage lobby
- Start games
- Route player inputs to games
- Update games
- Handle game completion
- Display results
- Return to idle
- Support rematches
- Prevent incompatible simultaneous games
- Reset games safely

Game code should not directly manipulate hardware.

Each game should return a frame or render state for the central renderer.

---

# 11. Mini-Games

Implement multiple mini-games. Prioritize making the mechanics genuinely fun rather than simply adding many incomplete games.

## Game 1: Shooter / LED Battle

### Concept

A shooter game designed specifically for a one-dimensional LED strip.

Players may join one of two teams or participate individually depending on the implementation.

The game should support multiple players.

### Gameplay concept

- Players occupy positions at one or both ends of the strip
- Players fire projectiles toward the center or toward opponents
- Enemies or targets spawn and move along the strip
- Targets must be hit before reaching a danger zone
- Projectiles move along the strip
- Collision detection happens between projectiles and targets
- Successful hits score points
- Targets may have different speeds or values
- Difficulty increases as the game progresses

### Controls

Use mobile-friendly controls.

Potential controls:

- Fire button
- Move left/right
- Swipe
- Team selection
- Optional rapid-fire control

Controls should be intuitive and require no physical buttons.

### Visuals

- Player positions
- Projectiles
- Enemies
- Explosions
- Hit feedback
- Score feedback
- Team colors
- Victory animation

The LED strip should make gameplay immediately understandable.

---

## Game 2: Dodge / Obstacle Survival

### Concept

A player controls an avatar moving along the strip while obstacles approach.

### Gameplay

- The player has a colored avatar
- Obstacles spawn at the opposite end or from either direction
- Obstacles move toward the player
- Player moves left/right to avoid obstacles
- Collisions result in damage, lost lives or game over
- Game speed increases over time
- Difficulty scales gradually

### Controls

Mobile browser controls:

- Left button
- Right button

Potential alternatives:

- Swipe left/right
- Tap a position on a virtual lane

Controls should be responsive and work on touchscreens.

### Visuals

- Player avatar
- Obstacles
- Warning indicators
- Collision feedback
- Lives
- Increasing difficulty
- Survival timer
- Score

The game should be designed specifically for a 60-pixel linear strip.

---

## Game 3: Reaction Race

### Concept

A competitive reaction-time game.

### Gameplay

1. Players join
2. Countdown begins
3. LEDs display a preparation animation
4. A random delay occurs
5. A target signal appears
6. Players press their controller button as quickly as possible
7. Reaction times are recorded
8. False starts are penalized
9. Results and winner are displayed

### Requirements

- Support multiple players
- Random timing to prevent prediction
- Detect false starts
- Record reaction times
- Show results
- Support multiple rounds
- Rank players
- Make the LED signal obvious

This game should be easy for anyone to understand in seconds.

---

## Game 4: Strip Pong

### Concept

A one-dimensional Pong game.

Ideally, it supports two players at opposite ends of the strip.

### Gameplay

- A ball travels along the LED strip
- Players are positioned at opposite ends
- When the ball reaches a player, they must hit it in time
- A successful hit reverses the ball direction
- Misses result in points for the opponent
- Ball speed increases over time
- Difficulty increases
- Score determines the winner

### Controls

- Tap HIT
- Optionally support timing windows
- Players can control their own side using their phones

### Visuals

- Ball
- Player indicators
- Hit zones
- Timing feedback
- Score
- Speed progression
- Victory animation

If necessary, start with a simple timing-based implementation and gradually improve it.

---

# 12. Additional Game Ideas

The framework should make adding games easy.

Potential future games:

## Snake

- Player controls a snake
- Collect food
- Snake grows
- Avoid collisions
- Use directional controls
- Suitable for solo gameplay

## Color Hunt

- A target color is shown
- Players try to reproduce/match it using controls
- Color difference determines score
- Multiple rounds

## Whack-a-Light

- A target LED appears
- Players race to press their button
- Targets move
- Wrong presses penalized
- Speed increases

## Territory Capture

- Players claim sections of the strip
- Players steal territory
- Score based on LED ownership
- Could support many players

## Simon / Memory

- LED color sequence appears
- Players reproduce the sequence
- Difficulty increases
- Multiplayer variants

## Last Survivor

- Players have colored positions
- Obstacles or danger zones appear
- Players must react and avoid elimination
- Last remaining player wins

Do not attempt to implement every future idea immediately. Focus on a stable framework and several well-designed games.

---

# 13. Website / UX

The website should be designed for mobile-first use.

Most players will access it from a phone while standing near the LED strip.

## Design goals

- Responsive
- Touch-friendly
- Fast loading
- Attractive
- Dark arcade aesthetic
- Large controls
- Easy to understand
- No app installation
- Works on common mobile browsers
- No external internet dependency

## Suggested visual style

A modern arcade aesthetic:

- Dark background
- Neon accents
- Glowing elements
- Player colors
- Rounded cards
- Large buttons
- Animated transitions
- Clear typography
- High contrast
- Responsive layout

Avoid overloading the UI with unnecessary information.

---

# 14. Main Screens

## Arcade Home / Attract Screen

Display:

- Arcade name/logo
- Current idle animation
- Available games
- Join instructions
- LAN URL
- QR code for joining
- Current number of players
- Start/join options

The QR code must sit on a white background with enough white quiet-zone
padding for reliable camera scanning. Keep the surrounding page, cards, and
arcade styling dark; only the QR image area needs the light background.

The home screen should make it obvious that the physical LED strip is active.

## Lobby

Display:

- Player list
- Player nicknames
- Player colors
- Ready status
- Game selection
- Host/start controls
- Countdown

## Game Selection

Display available games with:

- Game name
- Short description
- Number of players / recommended player count
- Difficulty
- Controls
- Start button

Player count should describe recommended gameplay, not necessarily impose a global player limit.

## Controller

The controller should adapt to the selected game.

Examples:

### Reaction game

Large:

```text
READY
```

Then:

```text
PRESS!
```

### Dodge

Large:

```text
← LEFT
RIGHT →
```

### Shooter

Large:

```text
FIRE
```

Optional movement controls.

### Pong

Large:

```text
HIT!
```

Controllers should be designed for touchscreens.

## Results screen

Display:

- Winner
- Scores
- Reaction times where relevant
- Survival time
- Ranking
- Rematch
- Return to arcade

---

# 15. Networking

The system should work entirely on the local network.

No cloud services should be required.

Players access the game via:

```text
http://<RASPBERRY_PI_IP>:5000
```

The web server should bind to:

```python
host="0.0.0.0"
```

Use an appropriate communication mechanism for live updates.

Preferred options:

- WebSockets
- Server-Sent Events
- Polling as a fallback

For a small local multiplayer application, avoid unnecessary networking complexity.

The website should receive:

- Current game state
- Player list
- Scores
- Countdown
- LED/game state
- Current mode
- Game status

Player inputs should be sent to the server with low latency.

The system should tolerate players disconnecting or refreshing their browser.

### Web microphone queue (implemented; HTTPS required for browsers)

Free music mode prefers one opted-in web user's microphone and falls back to
the Pi's ALSA input. Web mic users request the mic explicitly; one owner is
allowed at a time and other users queue FIFO. If anyone is waiting, the active
turn is handed off after the admin-configured duration (15 to 1800 seconds).
The previous owner's browser track is stopped on handoff, and users can leave
the queue. Browser audio is analyzed locally; only volume, peak, and clap
features are sent to the Pi. No audio is recorded or retained.

Browser mic access requires a secure origin (HTTPS or localhost) and user
permission. The default `http://<pi-ip>:5000` deployment is not a secure origin
for phone browsers, so web mic users need a trusted HTTPS URL; otherwise the
visualizer uses the Pi ALSA fallback. The interface explains this requirement.
The Pi fallback requires an ALSA capture device, such as a USB audio
interface; a GPIO-connected mic would need compatible audio conversion and
driver support, which is not part of the current hardware setup.

### Fairness plan for network delay (planned)

Implement latency handling in measured stages rather than subtracting an
assumed delay from every input:

1. Measure each phone's round-trip time and jitter during the lobby and
   throughout play. Track median and 95th-percentile values per player; report
   these in server logs without exposing them as a score.
2. Advance every game on a fixed server simulation tick using the server's
   monotonic clock. Give each input a player ID, sequence number, action, and
   client event timestamp; reject duplicates, out-of-order packets, and
   implausibly old/future timestamps.
3. For Reaction Race, keep the physical LED flash as the authoritative common
   cue. Estimate browser-to-server clock offset from repeated timestamped
   exchanges, and score the button's client event timestamp after conversion
   to server time. Bound the correction by measured RTT/jitter and retain an
   uncertainty value; do not treat RTT/2 as exact because the two network
   directions may differ. If uncertainty is too high, flag the round or use a
   generous tie window rather than pretending the result is precise.
4. For movement and hit games, batch input intents onto common future server
   ticks. Choose one input delay for the whole match from the slowest player's
   measured high-percentile latency plus a small safety margin, then keep it
   fixed for the match. This gives all players the same response window.
   Predict local controller feedback for responsiveness, then reconcile it to
   authoritative server state.
5. During play, buffer brief jitter spikes within the agreed input window.
   Discard inputs that arrive too late instead of applying them to a later
   game moment. For severe sustained lag or a disconnect, show a clear paused
   or reconnect state and resume from a server snapshot where the game allows.
6. Validate the approach with phones on the actual Wi-Fi, recording per-player
   median/p95 RTT, jitter, input arrival times, and perceived fairness. Keep
   Reaction Race timing separate from the movement-game input delay policy.

The current app does not implement clock synchronization, latency compensation,
fixed input ticks, or lag-aware pausing; this is a design plan only.

### Tutorial attention and ready gate

Do not start the game automatically when the timed tutorial animation ends.
Players cannot read a phone and watch the physical strip at the same time.
Present the phone instructions first, then explicitly cue players to look at
the strip while the shared LED demo runs; allow a player to replay the demo.
After the demo, show a per-player READY control and wait without a countdown
until every participant required for the selected game is ready. Only then
begin the game countdown. Keep readiness visible and let a player review or
replay the tutorial before marking ready. Before entering the tutorial, every
connected player in the lobby must also mark ready; this prevents one player
from starting before the group is prepared. Both readiness checks are now
implemented.

---

# 16. Idle/Lobby/Game Lifecycle

The arcade should have a clear lifecycle.

```text
BOOT
  │
  ▼
IDLE / ATTRACT
  │
  ├── Player joins
  │
  ▼
LOBBY
  │
  ├── Select game
  ├── Players ready
  └── Host starts
  │
  ▼
COUNTDOWN
  │
  ▼
ACTIVE GAME
  │
  ├── Game continues
  ├── Player inputs
  └── Game ends
  │
  ▼
RESULTS
  │
  ├── Rematch
  │
  └── Return to arcade
          │
          ▼
        IDLE
```

The LEDs must remain active throughout the lifecycle.

---

# 17. Admin / Configuration

Include basic configurable settings.

Potential settings:

- LED brightness
- Idle animation
- Idle animation duration
- Idle animation randomization
- Game duration
- Difficulty
- Number of rounds
- Free music input source: opted-in web microphone first, Pi ALSA fallback
- Web microphone queue handoff duration while other users are waiting
- Free music mode (implemented): capture the local microphone through ALSA,
  adapt the visualizer to ambient level, and flash on clap-like transients.
- Web-user microphone (implemented): browser-first visualizer input with
  explicit opt-in, one owner, FIFO queue, admin-configured handoff, local
  feature extraction, and Pi ALSA fallback. Trusted HTTPS is required for
  phone browsers; LAN HTTP falls back to the Pi input.
- Spotify playback integration (future; do not implement yet): connect to the
  owner's personal Spotify account over the LAN and offer a public website
  link where visitors can add tracks to a shared playback queue.
- Reset arcade
- Stop game
- Return to idle
- Restart application

The administrator interface can be simple.

Do not expose destructive or sensitive controls unnecessarily.

---

# 18. Performance and Reliability

The Raspberry Pi 4 should be able to run the game and website simultaneously.

Requirements:

- Efficient frame generation
- Avoid excessive CPU use
- Avoid unnecessary memory allocation in the rendering loop
- Avoid excessive network traffic
- Avoid blocking the LED renderer with web requests
- Ensure player input is processed promptly
- Handle exceptions without leaving the strip in an undesirable state
- Prevent multiple simultaneous games
- Prevent multiple renderers
- Prevent hardware initialization multiple times
- Avoid conflicting LED control processes

If the application exits or crashes, attempt to clear the LEDs safely where possible.

Use proper logging.

---

# 19. Security / LAN Scope

This is a local arcade, not a public internet service.

Requirements:

- Intended for trusted LAN access
- No account system required
- No cloud authentication
- Validate player names
- Sanitize browser-rendered content
- Validate game inputs
- Do not trust client-side scores or game state
- Server owns game state and scoring
- Prevent arbitrary API calls from controlling hardware outside the intended functionality

Do not expose the application to the internet without a separate security review.

---

# 20. Automatic Startup

Once the application is stable, configure it to run automatically after Raspberry Pi boot.

Use a systemd service.

The service should:

- Start the application
- Run using the required permissions
- Restart automatically if it crashes
- Log errors
- Start after networking is available
- Ensure there is only one instance
- Keep the LEDs active

Example intended command:

```bash
sudo /home/pi/neopixel-env/bin/python /home/pi/led_game.py
```

Do not configure autostart until the application has been tested manually.

---

# 21. Development Priorities

Implement in phases.

### Immediate next step: Vercel + Ably browser microphone path

Make the browser microphone usable without asking each LAN phone to trust a
locally generated certificate. Host the HTTPS website on Vercel and use Ably
as the realtime relay. The Raspberry Pi connects outward to Ably, so this
design must work behind ISP NAT without inbound port forwarding or a public
home IP address.

Keep the Raspberry Pi as the sole source of truth for arcade/game state and
the only LED renderer. Capture and analyze microphone audio in the web user's
browser; send only low-rate normalized level/peak/clap, coarse frequency-band,
and latency estimate features through Ably, never raw audio. The Pi validates microphone
ownership/lease messages before
using features for visualization. Keep any additional browser-to-Pi messages
limited to what the Vercel-hosted interface needs; do not move game authority
or LED rendering into Vercel, Ably, or MongoDB Atlas.

Use Vercel server-side authentication to issue short-lived, narrowly scoped
Ably credentials. Never expose the Ably API key in browser code. Preserve the
existing single-owner FIFO mic queue and admin handoff duration. Before
release, check Ably message quotas at the chosen sample rate and ensure the
website remains usable if the relay is unavailable. This is the immediate
next implementation task; it is not implemented yet.

## Phase 1 — Architecture and stability

- Inspect existing prototype
- Preserve working GPIO/NeoPixel configuration
- Create modular architecture
- Centralize rendering
- Implement continuous frame loop
- Add proper state management
- Add logging
- Ensure the web server and renderer coexist

## Phase 2 — Idle animations

Implement a minimum of:

- Rainbow wave
- Comet
- Twinkle
- Fire
- Color wave
- Christmas mode

Add animation transitions and automatic switching.

Ensure LEDs never go dark simply because nobody is playing.

## Phase 3 — Web arcade interface

- Responsive mobile UI
- Arcade home
- Player joining
- Lobby
- Player colors
- Game selection
- Controllers
- Results

## Phase 4 — Player system

- Unlimited players where practical
- Unique IDs
- Nicknames
- Color wheel assignment
- Player disconnect handling
- Ready states
- Host management

## Phase 5 — Games

Implement games in the following suggested order:

1. Reaction Race — easiest and immediately fun
2. Dodge — good solo game
3. Shooter — good multiplayer potential
4. Strip Pong — two-player competitive game

Prioritize quality over quantity.

## Phase 6 — Polish

- Animations
- Transitions
- Victory effects
- Per-player game sounds in the web client (future; play game cues only for each
  player's own browser while a game is active; no lobby, menu, or free-music
  mode sounds. Microphone-driven free music visualization is already implemented.)
- Spotify music-reactive LED mode and public queue link (roadmap only; not part
  of the current implementation)
- QR code
- Admin controls
- Performance improvements
- Bug fixes

## Phase 7 — Deployment

- systemd service
- Automatic startup
- Restart behavior
- Logging
- Headless operation
- LAN testing

---

# 22. Acceptance Criteria

The project should not be considered complete until:

### Hardware

- [ ] NeoPixel strip works with the existing Pi 4 setup
- [ ] Correct GPIO configuration retained
- [ ] Brightness configurable
- [ ] No conflicting LED control processes

### Idle mode

- [ ] LEDs animate continuously when no game is running
- [ ] Multiple idle animations exist
- [ ] Animations switch automatically
- [ ] Transitions are visually smooth
- [ ] LEDs do not remain dark unnecessarily

### Web interface

- [ ] Accessible from another LAN device
- [ ] Mobile responsive
- [ ] QR code has a white background and quiet zone while the rest of the UI stays dark
- [ ] No app installation required
- [ ] Players can join
- [ ] Player names and colors are visible
- [ ] Game selection works
- [ ] Controllers work on mobile

### Players

- [ ] No hard-coded global three-player limit
- [ ] Colors are distributed evenly around the hue wheel
- [ ] Colors are visually distinct
- [ ] Colors are stable during games
- [ ] Disconnections do not crash the application

### Games

- [ ] At least three genuinely playable mini-games
- [ ] Game mechanics work reliably
- [ ] Player input feels responsive
- [ ] Scores are calculated server-side
- [ ] Game completion is handled
- [ ] Results are displayed
- [ ] Rematch works
- [ ] Returning to idle works
- [ ] Tutorial presents phone instructions before directing attention to the LED demo
- [ ] Tutorial can be replayed, and game waits without a timer for all required players to mark ready

### Architecture

- [ ] One central LED renderer
- [ ] Games separated from hardware control
- [ ] Idle effects separated from games
- [ ] Game state managed centrally
- [ ] No conflicting LED writes
- [ ] Logs are available

### Deployment

- [ ] Application runs headlessly
- [ ] Automatic startup works
- [ ] Application restarts after crash
- [ ] LEDs return to idle mode appropriately
- [ ] Can be controlled remotely over SSH

### Free music mode

- [x] Web microphone is primary; Pi ALSA is fallback
- [x] At most one web microphone owner at a time
- [x] Other web microphone requests queue in FIFO order
- [x] Admin can configure the active user's queue handoff duration
- [x] Handoff notifies the current user, releases their media track, then activates the next queued user
- [x] Audio is not recorded or retained; only locally computed features are sent
- [x] Provide multiple selectable LED visualizer patterns
- [x] Add a six-band frequency spectrum for browser and Pi microphones
- [x] Estimate BPM from bass onsets and predict visual pulses using mic/network delay
- [x] Allow admin adjustment of predicted beat timing
- [x] Allow live web-UI pattern switching while music mode is active
- [x] Include a retro green/yellow/red VU color pattern
- [x] Include mirrored shapes that move inward from both strip ends
- [x] Include a full-strip pattern using shades of red only
- [x] Let users choose primary/accent colors from the music UI
- [x] Provide adjustable visualizer sensitivity for both mic sources
- [x] Estimate BPM from bass-band onsets and predict beat accents using mic/network latency
- [x] Add an admin timing trim for music beat prediction
- [x] Keep loud audio colors saturated; clap accents must not wash the strip white
- [ ] Provide a trusted HTTPS deployment URL so phone browsers can grant mic access
- [ ] Host the HTTPS website on Vercel and relay browser mic features to the Pi with Ably
- [ ] Keep game state and LED rendering authoritative on the Pi; relay no raw audio
- [ ] Issue short-lived, scoped Ably credentials from a Vercel server-side endpoint

---

# 23. Development Instructions for the Coding Agent

Before implementation:

1. Inspect the existing project and prototype.
2. Identify the currently working NeoPixel hardware setup.
3. Preserve the working `rpi_ws281x` implementation.
4. Understand the current Flask application.
5. Identify any useful code that can be reused.
6. Create a plan before making major changes.

During implementation:

- Prefer plug-and-play solutions, existing browser APIs, and proven reusable
  building blocks. Before writing custom code, inspect the repo and available
  libraries/tools for something that already solves the need. Avoid duplicating
  functionality or adding a dependency unless it fits the offline Pi setup.
- Favor clean, maintainable, modular code.
- Keep the architecture simple enough for a Raspberry Pi.
- Do not unnecessarily introduce complex dependencies.
- Do not replace working GPIO code without a compelling reason.
- Keep game logic independent of the hardware.
- Implement and test one game at a time.
- Ensure the idle mode is functional before implementing all games.
- Make the web interface mobile-first.
- Prioritize fun, visual feedback and responsiveness.
- Avoid placeholder games that technically work but are not enjoyable.
- Document installation, execution and troubleshooting.

Do not simply modify the old territory game. It should be treated as a prototype and its architecture may be replaced.

The ultimate goal is to create a **self-contained Raspberry Pi LED arcade that runs continuously, displays beautiful animations when idle, and allows people nearby to join and play fun games from their phones over Wi-Fi**.
