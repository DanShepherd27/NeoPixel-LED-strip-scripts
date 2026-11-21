"""A continuously moving rainbow across the strip."""

from led.colors import hsv_to_rgb


class RainbowWave:
    def __init__(self, count):
        self.count = count
        self.offset = 0.0
        self.speed = 80.0  # hue degrees per second

    def render(self, frame, dt):
        self.offset = (self.offset + self.speed * dt) % 360.0
        step = 360.0 / self.count
        for i in range(self.count):
            hue = (self.offset + i * step) % 360.0
            frame.set(i, hsv_to_rgb(hue, 1.0, 1.0))
