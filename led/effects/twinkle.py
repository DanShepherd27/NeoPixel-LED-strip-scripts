"""Twinkling stars: random pixels smoothly fade in and out."""

import random

from led.colors import hsv_to_rgb, dim


class Twinkle:
    def __init__(self, count):
        self.count = count
        self.brightness = [0.0] * count
        self.targets = [0.0] * count
        self.rates = [random.uniform(0.4, 1.5) for _ in range(count)]
        self.hues = [random.choice([0.0, 45.0, 190.0, 280.0, 320.0])
                     for _ in range(count)]

    def render(self, frame, dt):
        for i in range(self.count):
            # Move toward the target; pick a new target when reached.
            target = self.targets[i]
            current = self.brightness[i]
            if abs(target - current) < 0.01:
                self.targets[i] = random.random()
            else:
                step = self.rates[i] * dt
                if current < target:
                    current = min(target, current + step)
                else:
                    current = max(target, current - step)
                self.brightness[i] = current

            if current > 0.01:
                base = hsv_to_rgb(self.hues[i], 0.4, 1.0)
                frame.set(i, dim(base, current))
