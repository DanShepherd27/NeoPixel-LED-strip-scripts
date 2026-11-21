"""A smooth colour breathing / intensity pulse."""

import math

from led.colors import hsv_to_rgb


class Breathing:
    def __init__(self, count):
        self.count = count
        self.phase = 0.0
        self.hue = 0.0
        self.hue_speed = 30.0     # hue degrees/second
        self.frequency = 0.6      # pulse cycles/second

    def render(self, frame, dt):
        self.phase += dt
        self.hue = (self.hue + self.hue_speed * dt) % 360.0

        intensity = (math.sin(self.phase * self.frequency * 2.0 * math.pi)
                     + 1.0) / 2.0
        colour = hsv_to_rgb(self.hue, 0.8, intensity)
        frame.fill(colour)
