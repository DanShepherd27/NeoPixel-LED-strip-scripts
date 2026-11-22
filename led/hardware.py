"""Hardware abstraction for the NeoPixel strip.

Wraps the working ``rpi_ws281x`` library and falls back to a mock when it is
not available (e.g. developing/testing off the Pi). Nothing outside this file
should ever touch ``PixelStrip`` directly.
"""

import logging
import threading

log = logging.getLogger("led.hardware")


class LEDHardware:
    def __init__(self, count, pin, freq_hz, dma, invert, brightness, channel,
                 hidden_start=0, hidden_end=0, color_red=100,
                 color_green=100, color_blue=100):
        self.count = count
        self.hidden_start = max(0, min(count, int(hidden_start)))
        self.hidden_end = max(0, min(count - self.hidden_start, int(hidden_end)))
        self._offset_lock = threading.Lock()
        self.color_balance = (100, 100, 100)
        self.set_color_balance(color_red, color_green, color_blue)
        self.pin = pin
        self.freq_hz = freq_hz
        self.dma = dma
        self.invert = invert
        self.brightness = brightness
        self.channel = channel

        self.strip = None
        self.mock = True
        self.hardware_error = None

        try:
            from rpi_ws281x import PixelStrip
            self.strip = PixelStrip(
                count,
                pin,
                freq_hz,
                dma,
                invert,
                brightness,
                channel,
            )
            self.mock = False
        except Exception as exc:  # ImportError or hardware init failure
            self.hardware_error = str(exc)
            log.warning(
                "rpi_ws281x unavailable (%s); running in MOCK mode "
                "(no physical LEDs will be driven).", exc,
            )

    def begin(self):
        if self.strip is not None:
            try:
                self.strip.begin()
            except Exception as exc:
                self.hardware_error = str(exc)
                log.error("Failed to initialise NeoPixel hardware: %s", exc)
                self.strip = None
                self.mock = True

    def show_frame(self, frame):
        """Write a :class:`led.frame.Frame` to the physical strip."""
        if self.strip is None:
            return
        try:
            with self._offset_lock:
                hidden_start = self.hidden_start
                hidden_end = self.hidden_end
            visible_end = self.count - hidden_end
            for i in range(self.count):
                if i < hidden_start or i >= visible_end:
                    r, g, b = (0, 0, 0)
                elif i < len(frame.pixels):
                    r, g, b = frame.pixels[i]
                else:
                    r, g, b = (0, 0, 0)
                red_gain, green_gain, blue_gain = self.color_balance
                r = min(255, (r * red_gain + 50) // 100)
                g = min(255, (g * green_gain + 50) // 100)
                b = min(255, (b * blue_gain + 50) // 100)
                # rpi_ws281x packs colour as 24-bit int
                self.strip.setPixelColor(i, (r << 16) | (g << 8) | b)
            self.strip.show()
        except Exception as exc:
            self.hardware_error = str(exc)
            log.error("Error writing frame to hardware: %s", exc)
            self.strip = None
            self.mock = True

    def set_hidden_offsets(self, hidden_start, hidden_end):
        """Update the globally hidden LED counts at each physical end."""
        hidden_start = max(0, min(self.count, int(hidden_start)))
        hidden_end = max(0, min(self.count - hidden_start, int(hidden_end)))
        with self._offset_lock:
            self.hidden_start = hidden_start
            self.hidden_end = hidden_end

    def set_color_balance(self, red, green, blue):
        """Set global per-channel output scaling (percent, 0 to 200)."""
        balance = tuple(max(0, min(200, int(value))) for value in (red, green, blue))
        with self._offset_lock:
            self.color_balance = balance

    def set_brightness(self, brightness):
        self.brightness = max(0, min(255, int(brightness)))
        if self.strip is not None:
            try:
                self.strip.setBrightness(self.brightness)
            except Exception as exc:
                log.error("Error setting brightness: %s", exc)

    def clear(self):
        """Turn every pixel off."""
        if self.strip is None:
            return
        try:
            for i in range(self.count):
                self.strip.setPixelColor(i, 0)
            self.strip.show()
        except Exception as exc:
            log.error("Error clearing hardware: %s", exc)
