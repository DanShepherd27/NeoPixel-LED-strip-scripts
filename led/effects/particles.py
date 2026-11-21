"""Several coloured particles bouncing along the strip."""

import random

from led.colors import hsv_to_rgb, dim


class Particles:
    def __init__(self, count, n=5):
        self.count = count
        self.particles = []
        for i in range(n):
            self.particles.append({
                "pos": random.uniform(0, count - 1),
                "vel": random.choice([-1, 1]) * random.uniform(15, 45),
                "hue": (360.0 * i / n) % 360.0,
            })

    def render(self, frame, dt):
        for p in self.particles:
            p["pos"] += p["vel"] * dt
            if p["pos"] >= self.count - 1:
                p["pos"] = self.count - 1
                p["vel"] = -abs(p["vel"])
            elif p["pos"] <= 0:
                p["pos"] = 0.0
                p["vel"] = abs(p["vel"])

            head = int(round(p["pos"]))
            colour = hsv_to_rgb(p["hue"], 0.9, 1.0)
            # Draw a short trailing glow.
            for tail in range(3):
                idx = head - int(p["vel"] / abs(p["vel"])) * tail
                if 0 <= idx < self.count:
                    frame.blend(idx, colour, max(0.0, 1.0 - tail / 3.0))
