"""Christmas mode: festive red/green/gold/warm-white with sparkle and comets.

Combines alternating candy-cane bands, gentle random sparkle, a slow overall
pulse, and an occasional comet sweeping the strip.
"""

import random
import math

from led.colors import hsv_to_rgb, dim, blend

RED = (200, 20, 20)
GREEN = (20, 180, 40)
GOLD = (230, 180, 40)
WARM_WHITE = (240, 220, 180)


class Christmas:
    def __init__(self, count):
        self.count = count
        self.pulse_phase = 0.0

        # Sparkle state.
        self.sparkles = {}  # index -> remaining brightness (0..1)

        # Comet state.
        self.comet_pos = -1.0
        self.comet_dir = 1
        self.comet_speed = 45.0
        self.comet_timer = random.uniform(4.0, 8.0)

        # Base palette: alternating red/green candy-cane.
        self.base = [RED if i % 2 == 0 else GREEN for i in range(count)]

    def render(self, frame, dt):
        self.pulse_phase += dt

        # Slow breathing pulse (0.75 .. 1.0).
        pulse = 0.85 + 0.15 * (math.sin(self.pulse_phase * 1.2) + 1.0) / 2.0

        # Candy-cane base with occasional gold/warm-white accents.
        for i in range(self.count):
            if i % 12 == 5:
                colour = GOLD
            elif i % 12 == 9:
                colour = WARM_WHITE
            else:
                colour = self.base[i]
            frame.set(i, dim(colour, pulse))

        # Sparkle: random pixels flare then fade.
        if random.random() < 0.3:
            self.sparkles[random.randrange(self.count)] = 1.0
        for idx in list(self.sparkles.keys()):
            frame.set(idx, WARM_WHITE)
            self.sparkles[idx] -= dt * 1.5
            if self.sparkles[idx] <= 0.0:
                del self.sparkles[idx]

        # Occasional comet.
        self.comet_timer -= dt
        if self.comet_timer <= 0.0 and self.comet_pos < 0:
            self.comet_pos = 0.0
            self.comet_dir = 1
        if self.comet_pos >= 0:
            self.comet_pos += self.comet_dir * self.comet_speed * dt
            if self.comet_pos >= self.count - 1:
                self.comet_pos = self.count - 1
                self.comet_dir = -1
            elif self.comet_pos <= 0:
                self.comet_pos = -1.0
                self.comet_timer = random.uniform(4.0, 8.0)

            head = int(round(self.comet_pos))
            for tail in range(6):
                idx = head - self.comet_dir * tail
                if 0 <= idx < self.count:
                    frame.blend(idx, WARM_WHITE, max(0.0, 1.0 - tail / 6.0))
