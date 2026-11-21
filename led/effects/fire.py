"""A 1D fire / ember simulation.

Heat is seeded at one end of the strip and propagates toward the other with a
simple neighbour-averaging + cooling diffusion, mapped to red/orange/yellow.
"""

import random

from led.colors import hsv_to_rgb


class Fire:
    def __init__(self, count, cooling=0.06, sparking=4):
        self.count = count
        self.cooling = cooling
        self.sparking = sparking  # how many source pixels get re-seeded/frame
        self.heat = [0.0] * count

    def _render(self, frame):
        # Cool every pixel a little.
        for i in range(self.count):
            self.heat[i] = max(0.0, self.heat[i] - random.random() * self.cooling)

        # Diffuse: average each pixel with its neighbours.
        previous = self.heat[:]
        for i in range(1, self.count - 1):
            self.heat[i] = (previous[i - 1] + previous[i] + previous[i + 1]) / 3.0

        # Seed the base (we treat the end of the strip as the fuel source).
        for _ in range(self.sparking):
            idx = random.randint(max(0, self.count - 6), self.count - 1)
            self.heat[idx] = min(1.0, self.heat[idx] + random.random() * 0.8)

        for i in range(self.count):
            value = self.heat[i]
            if value <= 0.0:
                frame.set(i, (0, 0, 0))
                continue
            # Low heat -> deep red, high heat -> yellow/white.
            hue = max(0.0, 20.0 - value * 40.0)  # ~20deg (red) down toward orange
            frame.set(i, hsv_to_rgb(hue, 1.0, min(1.0, value * 1.4)))

    def render(self, frame, dt):
        self._render(frame)
