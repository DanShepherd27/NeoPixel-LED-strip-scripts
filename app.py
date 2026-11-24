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
    SONG_AUDIO_LATENCY_MS, GAME_SOUNDS, OUTPUT_AUDIO_DEVICE,
    BLUETOOTH_AUDIO_DEVICE, BLUETOOTH_LATENCY_MS,
)
from led.hardware import LEDHardware
from led.audio import AudioInput
from led.audio_sources import BluetoothSource
from led.bluetooth_audio import BluetoothAudioInput
from led.pcm_sink import AplaySink
from led.renderer import Renderer
from arcade.manager import ArcadeManager
from arcade.bluetooth_sync import BluetoothDelaySync
from arcade.music_animations import MUSIC_ANIMATIONS
from arcade.sounds import SoundPlayer
from web.runtime_settings import update_runtime_settings
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
    music_glitter_brightness = 255
    music_glitter_every_beats = 8
    music_beat_lead_ms = MUSIC_BEAT_LEAD_MS
    music_primary_color = MUSIC_PRIMARY_COLOR
    music_accent_color = MUSIC_ACCENT_COLOR
    music_band_colors = list(MUSIC_BAND_COLORS)
    color_red, color_green, color_blue = LED_COLOR_RED, LED_COLOR_GREEN, LED_COLOR_BLUE
    brightness = LED_BRIGHTNESS
    preview_invert_order = False
    song_audio_latency_ms = SONG_AUDIO_LATENCY_MS
    song_auto_sync = True
    music_input = "microphone"
    bluetooth_latency_ms = BLUETOOTH_LATENCY_MS
    bluetooth_auto_sync = True
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
        music_glitter_brightness = int(saved.get("music_glitter_brightness", music_glitter_brightness))
        music_glitter_every_beats = int(saved.get("music_glitter_every_beats", music_glitter_every_beats))
        music_beat_lead_ms = int(saved.get("music_beat_lead_ms", music_beat_lead_ms))
        music_primary_color = saved.get("music_primary_color", music_primary_color)
        music_accent_color = saved.get("music_accent_color", music_accent_color)
        music_band_colors = saved.get("music_band_colors", music_band_colors)
        color_red = int(saved.get("led_color_red", color_red))
        color_green = int(saved.get("led_color_green", color_green))
        color_blue = int(saved.get("led_color_blue", color_blue))
        brightness = int(saved.get("led_brightness", brightness))
        preview_invert_order = saved.get("preview_invert_order", preview_invert_order)
        song_audio_latency_ms = int(saved.get("song_audio_latency_ms", song_audio_latency_ms))
        song_auto_sync = saved.get("song_auto_sync", song_auto_sync)
        music_input = saved.get("music_input", music_input)
        bluetooth_latency_ms = int(saved.get("bluetooth_latency_ms", bluetooth_latency_ms))
        bluetooth_auto_sync = saved.get("bluetooth_auto_sync", bluetooth_auto_sync)
        if type(bluetooth_auto_sync) is not bool:
            raise ValueError("saved Bluetooth auto-sync must be a boolean")
        if music_input not in ("microphone", "bluetooth"):
            raise ValueError("saved sound source is not supported")
        if not 0 <= bluetooth_latency_ms <= 1500:
            raise ValueError("saved Bluetooth latency must be between 0 and 1500 ms")
        if hidden_start < 0 or hidden_end < 0 or hidden_start + hidden_end > LED_COUNT:
            raise ValueError("saved LED offsets are outside the valid strip range")
        if any(not 0 <= value <= 200 for value in (color_red, color_green, color_blue)):
            raise ValueError("saved LED color balance must be between 0 and 200 percent")
        if not 0 <= brightness <= 255:
            raise ValueError("saved LED brightness must be between 0 and 255")
        if type(preview_invert_order) is not bool:
            raise ValueError("saved preview order inversion must be a boolean")
        if not 0 <= song_audio_latency_ms <= 1500 or type(song_auto_sync) is not bool:
            raise ValueError("saved song latency must be 0-1500 ms and auto-sync a boolean")
        if not 15 <= mic_handoff_seconds <= 1800:
            raise ValueError("saved microphone handoff must be between 15 and 1800 seconds")
        if music_animation not in MUSIC_ANIMATIONS:
            raise ValueError("saved music animation is not supported")
        if not 0.25 <= music_sensitivity <= 4.0:
            raise ValueError("saved music sensitivity must be between 0.25 and 4.0")
        if music_sound_profile not in ("balanced", "small_speakers", "bass_forward"):
            raise ValueError("saved sound profile is not supported")
        if not 0 <= music_glitter_brightness <= 255:
            raise ValueError("saved glitter brightness must be between 0 and 255")
        if music_glitter_every_beats not in (2, 4, 8, 16, 32):
            raise ValueError("saved glitter interval must be 2, 4, 8, 16, or 32 beats")
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
        music_glitter_brightness = 255
        music_glitter_every_beats = 8
        music_beat_lead_ms = MUSIC_BEAT_LEAD_MS
        music_primary_color, music_accent_color = MUSIC_PRIMARY_COLOR, MUSIC_ACCENT_COLOR
        music_band_colors = list(MUSIC_BAND_COLORS)
        color_red, color_green, color_blue = LED_COLOR_RED, LED_COLOR_GREEN, LED_COLOR_BLUE
        brightness = LED_BRIGHTNESS
        preview_invert_order = False
        song_audio_latency_ms, song_auto_sync = SONG_AUDIO_LATENCY_MS, True
        music_input, bluetooth_latency_ms = "microphone", BLUETOOTH_LATENCY_MS
        bluetooth_auto_sync = True

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
    bluetooth_input = BluetoothAudioInput(BLUETOOTH_AUDIO_DEVICE, AplaySink(OUTPUT_AUDIO_DEVICE))
    bluetooth_input.start()
    manager = ArcadeManager(
        LED_COUNT, audio_input, mic_handoff_seconds,
        music_animation, music_sensitivity, music_primary_color, music_accent_color,
        music_beat_lead_ms, music_band_colors, music_sound_profile,
        music_glitter_brightness, music_glitter_every_beats,
        extra_music_sources=[BluetoothSource(bluetooth_input, bluetooth_latency_ms, BluetoothDelaySync(
            bluetooth_input, audio_input, bluetooth_auto_sync,
            on_learned=lambda ms: update_runtime_settings({"bluetooth_latency_ms": ms})))],
        music_input=music_input,
    )
    manager.preview_invert_order = preview_invert_order
    manager.hidden_offsets = hardware.visible_range
    manager.sounds = SoundPlayer(OUTPUT_AUDIO_DEVICE, GAME_SOUNDS)
    manager.song_audio_latency_ms = song_audio_latency_ms
    manager.song_auto_sync = song_auto_sync
    manager.on_song_latency_changed = lambda ms: update_runtime_settings(
        {"song_audio_latency_ms": ms})

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
        bluetooth_input.stop()
        hardware.clear()


if __name__ == "__main__":
    main()
