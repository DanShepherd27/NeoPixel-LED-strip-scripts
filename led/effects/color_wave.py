"""Multiple colour bands travelling along the strip as a wave."""

from led.colors import hsv_to_rgb


class ColorWave:
    def __init__(self, count, bands=3):
        self.count = count
        self.bands = bands
        self.wavelength = max(6, count // max(1, bands))
        self.offset = 0.0
        self.speed = 30.0  # LEDs per second

    def render(self, frame, dt):
        self.offset = (self.offset + self.speed * dt) % self.count
        for i in range(self.count):
            # A band repeats every ``wavelength`` pixels; map to a hue.
            band_index = int((i + self.offset) // self.wavelength)
            hue = (band_index * 360.0 / self.bands) % 360.0
            frame.set(i, hsv_to_rgb(hue, 1.0, 0.9))
