"""Volume dynamics for live patterns: how loud the music is against its own recent
loudest moments, and sudden jumps in loudness.

Raw levels depend on the room, the microphone and the volume knob. Measuring against
the recent ceiling makes "loud" mean loud *for this song*, so quiet passages dim and
big moments open up without anyone adjusting sensitivity. ``surge`` catches hits even
when the beat tracker has not locked yet.
"""

import math

FLOOR = 0.03              # quieter than this is silence, not a quiet passage
POP_SECONDS = 0.14        # a hit fades like a stage flash: visible for ~150 ms at any tempo


def pop(seconds_since_beat, accent=1.0):
    """Brightness envelope of a hit ``seconds_since_beat`` ago (1.0 on the beat)."""
    return math.exp(-max(0.0, seconds_since_beat) / POP_SECONDS) * (0.6 + 0.4 * accent)


def live_pop(ctx):
    """The beat's pop for a live context: on the predicted beat once locked, else the
    detected kick (whose own envelope already fades over ~110 ms)."""
    if ctx.locked:
        return pop(ctx.phase * ctx.period, ctx.accent)
    return ctx.kick_hit


def follow(current, target, dt, attack, release):
    """Exponential follower: ``attack`` per second toward louder, ``release`` back down."""
    rate = attack if target > current else release
    return current + (target - current) * (1.0 - math.exp(-dt * rate))


class Dynamics:
    CEILING_FALL = 8.0    # seconds for the ceiling to fall by 1/e after a loud moment
    SURGE_DECAY = 7.0     # per second

    def __init__(self):
        self.fast = 0.0
        self.slow = None
        self.ceiling = FLOOR
        self.energy = 0.0     # 0-1: loudness against the recent ceiling
        self.surge = 0.0      # 0-1 envelope of a sudden jump in loudness

    def update(self, level, dt):
        dt = max(0.0, dt)
        level = max(0.0, level)
        self.fast = follow(self.fast, level, dt, 30.0, 6.0)
        self.slow = level if self.slow is None else follow(self.slow, level, dt, 1.5, 1.5)
        self.ceiling = max(FLOOR, self.fast, self.ceiling * math.exp(-dt / self.CEILING_FALL))
        self.energy = min(1.0, self.fast / self.ceiling) if self.fast > FLOOR else 0.0
        jump = max(0.0, self.fast - 1.2 * self.slow) / self.ceiling
        self.surge = max(min(1.0, 3.0 * jump), self.surge * math.exp(-dt * self.SURGE_DECAY))
        return self
