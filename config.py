"""Central configuration for the Raspberry Pi NeoPixel LED arcade.

Values here are the known-working hardware settings from the existing
prototype. Keep them together so nothing is hard-coded in the modules.
"""

import os

# ---------------------------------------------------------------------------
# LED hardware (do not change without a good reason — this is the working
# configuration from /home/pi/led_game.py).
# ---------------------------------------------------------------------------
LED_COUNT = 60
# Number of physical LEDs hidden at each end of the strip. These remain dark
# across every scene; the rest of the application still uses LED_COUNT pixels.
LED_HIDDEN_START = 0
LED_HIDDEN_END = 0
# Physical mounting direction; available values are "horizontal"/"vertical".
LED_ORIENTATION = "vertical"
LED_PIN = 18            # GPIO18 = physical pin 12
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 40     # 0-255; runtime master brightness is saved by admin settings
LED_INVERT = False
LED_CHANNEL = 0
# Per-channel output balance for matching the physical strip to chosen colors.
# Percentages are applied to every rendered pixel before it reaches the LEDs.
LED_COLOR_RED = 100
LED_COLOR_GREEN = 100
LED_COLOR_BLUE = 100

# ---------------------------------------------------------------------------
# Web server
# ---------------------------------------------------------------------------
HOST = "0.0.0.0"
PORT = 5000

# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
FPS = 40
FRAME_INTERVAL = 1.0 / FPS

# ---------------------------------------------------------------------------
# Idle / attract mode
# ---------------------------------------------------------------------------
IDLE_ANIMATION_DURATION = 25.0   # seconds each idle effect runs
IDLE_RANDOM_ORDER = True         # shuffle the playlist each cycle

# ---------------------------------------------------------------------------
# Arcade lifecycle timing
# ---------------------------------------------------------------------------
COUNTDOWN_SECONDS = 3.0
RESULTS_DURATION = 12.0

# ---------------------------------------------------------------------------
# Player / colour
# ---------------------------------------------------------------------------
MAX_NAME_LENGTH = 16
PLAYER_TIMEOUT = 20.0            # seconds before a silent player is dropped

# Admin settings. Set LED_ARCADE_ADMIN_PASSWORD in the service environment.
ADMIN_PASSWORD = os.environ.get("LED_ARCADE_ADMIN_PASSWORD", "")
AUDIO_DEVICE = os.environ.get("LED_AUDIO_DEVICE", "default")
WEB_MIC_HANDOFF_SECONDS = int(os.environ.get("LED_WEB_MIC_HANDOFF_SECONDS", "120"))
MUSIC_VISUALIZER = "retro_vu"
MUSIC_SENSITIVITY = 1.0
MUSIC_BEAT_LEAD_MS = int(os.environ.get("LED_MUSIC_BEAT_LEAD_MS", "0"))
MUSIC_PRIMARY_COLOR = "#00E5FF"
MUSIC_ACCENT_COLOR = "#FF2EA6"
MUSIC_BAND_COLORS = (
    "#FF2C0C", "#FF7A00", "#FFDC00", "#24FF20", "#00CDFF", "#AA20FF",
)
RUNTIME_SETTINGS_FILE = os.environ.get(
    "LED_ARCADE_SETTINGS_FILE",
    os.path.join(os.path.dirname(__file__), "runtime-settings.json"),
)

# Full-song light show. Delay between starting the Pi audio player and sound
# leaving the speakers; raise it if lights lead the music, lower it if they lag.
SONG_AUDIO_LATENCY_MS = int(os.environ.get("LED_SONG_AUDIO_LATENCY_MS", "250"))
# ALSA output for the song; defaults to the microphone's device so a USB audio
# card (or other combined input/output) plays through its own speaker jack.
OUTPUT_AUDIO_DEVICE = os.environ.get("LED_OUTPUT_AUDIO_DEVICE", AUDIO_DEVICE)

# Songs added through the website (analyzed on the Pi) live here, outside the
# deployed code so redeploying never touches them.
SONG_UPLOAD_DIR = os.environ.get(
    "LED_SONG_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "user-songs"))

# Retro game sound effects on the Pi's speaker (OUTPUT_AUDIO_DEVICE); "0" mutes them.
GAME_SOUNDS = os.environ.get("LED_ARCADE_GAME_SOUNDS", "1") != "0"
