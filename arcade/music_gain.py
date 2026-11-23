"""Automatic gain for live music features.

Sources report level and bands where 1.0 is the calibrated "loud" point but
louder music may exceed it. Clipping those at 1.0 pins every pattern at full
size, so each feature is divided by a ceiling that jumps up to new maxima and
relaxes slowly, never below 1.0 (quiet music keeps its calibrated scale).
"""

import math


class AutoGain:
    RELEASE_PER_SECOND = 0.08   # the ceiling halves in about 9 s of quieter music

    def __init__(self, channels):
        self.ceilings = [1.0] * channels

    def apply(self, values, dt):
        decay = math.exp(-max(0.0, dt) * self.RELEASE_PER_SECOND)
        scaled = []
        for index, value in enumerate(values):
            value = max(0.0, float(value))
            ceiling = max(1.0, value, self.ceilings[index] * decay)
            self.ceilings[index] = ceiling
            scaled.append(min(1.0, value / ceiling))
        return scaled
