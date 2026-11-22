"""Entry point for the Raspberry Pi NeoPixel LED arcade.

Run with the project's virtual environment (elevated as required by GPIO):

    sudo /home/pi/neopixel-env/bin/python /home/pi/app.py

Pass ``--mock`` to force mock hardware mode (no physical LEDs) for testing on
a machine without the rpi_ws281x library.
"""

import argparse
import logging
import json
import os
import re

from config import (
    LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_BRIGHTNESS,
    LED_HIDDEN_START, LED_HIDDEN_END,
    LED_COLOR_RED, LED_COLOR_GREEN, LED_COLOR_BLUE,
    LED_INVERT, LED_CHANNEL, HOST, PORT, FPS,
    RUNTIME_SETTINGS_FILE, AUDIO_DEVICE,
    WEB_MIC_HANDOFF_SECONDS,
    MUSIC_VISUALIZER, MUSIC_SENSITIVITY,
    MUSIC_BEAT_LEAD_MS,
    MUSIC_PRIMARY_COLOR, MUSIC_ACCENT_COLOR, MUSIC_BAND_COLORS,
)
from led.hardware import LEDHardware
from led.audio import AudioInput
from led.renderer import Renderer
from arcade.manager import ArcadeManager
from web.server import create_app


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)-18s %(levelname)-7s %(message)s",
    )


def main():
    parser = argparse.ArgumentParser(description="NeoPixel LED arcade")
    parser.add_argument("--mock", action="store_true",
                        help="Force mock hardware (no physical LEDs)")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    setup_logging()
    log = logging.getLogger("app")

    hidden_start, hidden_end = LED_HIDDEN_START, LED_HIDDEN_END
    mic_handoff_seconds = WEB_MIC_HANDOFF_SECONDS
    music_animation = MUSIC_VISUALIZER
    music_sensitivity = MUSIC_SENSITIVITY
    music_sound_profile = "small_speakers"
    music_beat_lead_ms = MUSIC_BEAT_LEAD_MS
    music_primary_color = MUSIC_PRIMARY_COLOR
    music_accent_color = MUSIC_ACCENT_COLOR
    music_band_colors = list(MUSIC_BAND_COLORS)
    color_red, color_green, color_blue = LED_COLOR_RED, LED_COLOR_GREEN, LED_COLOR_BLUE
    brightness = LED_BRIGHTNESS
    preview_invert_order = False
    try:
        with open(RUNTIME_SETTINGS_FILE, "r", encoding="utf-8") as settings_file:
            saved = json.load(settings_file)
        if not isinstance(saved, dict):
            raise ValueError("saved LED settings must be a JSON object")
        hidden_start = int(saved.get("hidden_start", hidden_start))
        hidden_end = int(saved.get("hidden_end", hidden_end))
        mic_handoff_seconds = int(saved.get("mic_handoff_seconds", mic_handoff_seconds))
        music_animation = saved.get("music_animation", music_animation)
        music_sensitivity = float(saved.get("music_sensitivity", music_sensitivity))
        music_sound_profile = saved.get("music_sound_profile", music_sound_profile)
        music_beat_lead_ms = int(saved.get("music_beat_lead_ms", music_beat_lead_ms))
        music_primary_color = saved.get("music_primary_color", music_primary_color)
        music_accent_color = saved.get("music_accent_color", music_accent_color)
        music_band_colors = saved.get("music_band_colors", music_band_colors)
        color_red = int(saved.get("led_color_red", color_red))
        color_green = int(saved.get("led_color_green", color_green))
        color_blue = int(saved.get("led_color_blue", color_blue))
        brightness = int(saved.get("led_brightness", brightness))
        preview_invert_order = saved.get("preview_invert_order", preview_invert_order)
        if hidden_start < 0 or hidden_end < 0 or hidden_start + hidden_end > LED_COUNT:
            raise ValueError("saved LED offsets are outside the valid strip range")
        if any(not 0 <= value <= 200 for value in (color_red, color_green, color_blue)):
            raise ValueError("saved LED color balance must be between 0 and 200 percent")
        if not 0 <= brightness <= 255:
            raise ValueError("saved LED brightness must be between 0 and 255")
        if type(preview_invert_order) is not bool:
            raise ValueError("saved preview order inversion must be a boolean")
        if not 15 <= mic_handoff_seconds <= 1800:
            raise ValueError("saved microphone handoff must be between 15 and 1800 seconds")
        if music_animation not in (
            "center_pulse", "mirror_bars", "rainbow_wave", "comet",
            "retro_vu", "inward_diamonds", "red_shades", "live_band", "bpm_trace", "laser_dance", "kitt_scanner",
        ):
            raise ValueError("saved music animation is not supported")
        if not 0.25 <= music_sensitivity <= 4.0:
            raise ValueError("saved music sensitivity must be between 0.25 and 4.0")
        if music_sound_profile not in ("balanced", "small_speakers", "bass_forward"):
            raise ValueError("saved sound profile is not supported")
        if not -100 <= music_beat_lead_ms <= 200:
            raise ValueError("saved music beat offset must be between -100 and 200 milliseconds")
        if not all(isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color)
                   for color in (music_primary_color, music_accent_color)):
            raise ValueError("saved music colors must use #RRGGBB format")
        if (not isinstance(music_band_colors, list) or len(music_band_colors) != 6 or
                not all(isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color)
                        for color in music_band_colors)):
            raise ValueError("saved music band colors must contain six #RRGGBB values")
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        log.warning("Ignoring invalid runtime LED settings: %s", exc)
        hidden_start, hidden_end = LED_HIDDEN_START, LED_HIDDEN_END
        mic_handoff_seconds = WEB_MIC_HANDOFF_SECONDS
        music_animation, music_sensitivity = MUSIC_VISUALIZER, MUSIC_SENSITIVITY
        music_sound_profile = "small_speakers"
        music_beat_lead_ms = MUSIC_BEAT_LEAD_MS
        music_primary_color, music_accent_color = MUSIC_PRIMARY_COLOR, MUSIC_ACCENT_COLOR
        music_band_colors = list(MUSIC_BAND_COLORS)
        color_red, color_green, color_blue = LED_COLOR_RED, LED_COLOR_GREEN, LED_COLOR_BLUE
        brightness = LED_BRIGHTNESS
        preview_invert_order = False

    hardware = LEDHardware(
        LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT,
        brightness, LED_CHANNEL,
        hidden_start, hidden_end, color_red, color_green, color_blue,
    )
    if args.mock:
        hardware.strip = None
        hardware.mock = True

    audio_input = AudioInput(AUDIO_DEVICE)
    audio_input.start()
    manager = ArcadeManager(
        LED_COUNT, audio_input, mic_handoff_seconds,
        music_animation, music_sensitivity, music_primary_color, music_accent_color,
        music_beat_lead_ms, music_band_colors, music_sound_profile,
    )
    manager.preview_invert_order = preview_invert_order

    renderer = Renderer(hardware, FPS)
    renderer.set_scene(manager)
    renderer.start()

    app, socketio = create_app(manager, hardware)

    log.info("Starting web server on %s:%d", HOST, args.port)
    try:
        socketio.run(
            app,
            host=HOST,
            port=args.port,
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True,
        )
    except KeyboardInterrupt:
        log.info("Shutting down")
    finally:
        renderer.stop()
        audio_input.stop()
        hardware.clear()


if __name__ == "__main__":
    main()
