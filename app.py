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

from config import (
    LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_BRIGHTNESS,
    LED_HIDDEN_START, LED_HIDDEN_END,
    LED_INVERT, LED_CHANNEL, HOST, PORT, FPS,
    RUNTIME_SETTINGS_FILE, AUDIO_DEVICE,
    WEB_MIC_HANDOFF_SECONDS,
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
    try:
        with open(RUNTIME_SETTINGS_FILE, "r", encoding="utf-8") as settings_file:
            saved = json.load(settings_file)
        if not isinstance(saved, dict):
            raise ValueError("saved LED settings must be a JSON object")
        hidden_start = int(saved.get("hidden_start", hidden_start))
        hidden_end = int(saved.get("hidden_end", hidden_end))
        mic_handoff_seconds = int(saved.get("mic_handoff_seconds", mic_handoff_seconds))
        if hidden_start < 0 or hidden_end < 0 or hidden_start + hidden_end > LED_COUNT:
            raise ValueError("saved LED offsets are outside the valid strip range")
        if not 15 <= mic_handoff_seconds <= 1800:
            raise ValueError("saved microphone handoff must be between 15 and 1800 seconds")
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        log.warning("Ignoring invalid runtime LED settings: %s", exc)
        hidden_start, hidden_end = LED_HIDDEN_START, LED_HIDDEN_END
        mic_handoff_seconds = WEB_MIC_HANDOFF_SECONDS

    hardware = LEDHardware(
        LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT,
        LED_BRIGHTNESS, LED_CHANNEL,
        hidden_start, hidden_end,
    )
    if args.mock:
        hardware.strip = None
        hardware.mock = True

    audio_input = AudioInput(AUDIO_DEVICE)
    audio_input.start()
    manager = ArcadeManager(LED_COUNT, audio_input, mic_handoff_seconds)

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
