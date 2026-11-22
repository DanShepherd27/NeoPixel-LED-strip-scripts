"""Calm and intimate moods: bells, verses, the whispered bridge, the outro.

Even the quiet looks keep a visible pulse: the strip is split into four
quarters and the current beat of the bar lights its quarter, so you can read
"1-2-3-4" off the strip while the music plays.
"""

import math
import random

from arcade.song.effects import (
    GOLD, GREEN, ICE, RED, SNOW, WARM, Comets, Sparkles, add, add_all, scaled, segment,
)
from led.colors import blend


class Bells:
    """Intro: sleigh-bell glints on the 8th-note grid, growing as the song wakes."""

    def __init__(self):
        self.sparkles = Sparkles(2.2)

    def render(self, frame, ctx):
        odds = (0.15 + 0.7 * max(ctx.bands[4], ctx.bands[5])) * (0.3 + ctx.progress)
        if ctx.new_eighth and random.random() < odds:
            for _ in range(1 + int(3 * ctx.progress)):
                self.sparkles.spawn(random.randrange(frame.count), random.choice((WARM, GOLD, SNOW)))
        glow = 0.03 + 0.10 * ctx.progress
        for index in range(frame.count):
            frame.pixels[index] = scaled(GOLD, glow * (0.4 + 0.6 * ctx.hit))
        self.sparkles.draw(frame, ctx.dt, 0.6 + 0.4 * ctx.progress)


class Verse:
    """Warm candy stripes that step on every beat, with a comet each bar."""

    def __init__(self, colors=(RED, WARM), lively=False):
        self.colors = colors
        self.lively = lively
        self.comets = Comets()

    def render(self, frame, ctx):
        per_beat = 2 if self.lively else 1
        shift = ctx.stepped(per_beat) * (2 if self.lively else 3)
        voice = max(ctx.bands[2], ctx.bands[3])
        base = 0.10 + 0.10 * voice
        for index in range(frame.count):
            stripe = int((index + shift) // 6) % 2
            frame.pixels[index] = scaled(self.colors[stripe], base)
        # The beat counter: this beat's quarter of the strip snaps on and fades.
        for index in segment(frame, ctx.beat_in_bar):
            stripe = int((index + shift) // 6) % 2
            color = GOLD if ctx.is_downbeat else self.colors[stripe]
            add(frame, index, scaled(color, 0.75 * ctx.hit))
        if ctx.is_backbeat:  # the snare: a whole-strip warm lift
            add_all(frame, scaled(WARM, 0.22 * ctx.hit))
        if self.lively:
            add_all(frame, scaled(self.colors[0], 0.18 * ctx.offbeat_hit))
        if ctx.new_bar:
            direction = 1 if ctx.bar_in_section % 2 == 0 else -1
            self.comets.launch(direction, 38.0, GOLD, 9 if self.lively else 7, frame.count)
        self.comets.draw(frame, ctx.dt, 0.8 + 0.2 * ctx.level)


class Whisper:
    """The quiet "make my wish come true" moment: icy shimmer and a star."""

    def __init__(self):
        self.phases = [random.uniform(0, math.tau) for _ in range(120)]

    def render(self, frame, ctx):
        breathe = 0.55 + 0.45 * math.sin(ctx.bar_position * math.pi * 2 - math.pi / 2)
        for index in range(frame.count):
            shimmer = 0.5 + 0.5 * math.sin(ctx.t * 1.7 + self.phases[index])
            color = blend(ICE, SNOW, shimmer * 0.6)
            frame.pixels[index] = scaled(color, 0.03 + 0.10 * shimmer * breathe)
        star = 0.40 + 0.25 * max(ctx.bands[3], ctx.bands[4]) + 0.30 * ctx.hit
        for offset in range(5):
            add(frame, frame.count - 1 - offset, scaled(GOLD, star * (1 - offset * 0.18)))
        add_all(frame, scaled(SNOW, 0.05 * ctx.hit))


class Afterglow:
    """Outro: warm twinkles that fade out with the music, still ticking the beat."""

    def __init__(self):
        self.sparkles = Sparkles(1.4)

    def render(self, frame, ctx):
        fade = min(1.0, ctx.level / 0.5)
        if ctx.new_beat:
            for _ in range(2):
                self.sparkles.spawn(random.randrange(frame.count),
                                    random.choice((WARM, GOLD, RED, GREEN)))
        for index in range(frame.count):
            frame.pixels[index] = scaled(GOLD, 0.04 * fade)
        add_all(frame, scaled(GOLD, 0.10 * ctx.hit * fade))
        self.sparkles.draw(frame, ctx.dt, 0.3 + 0.7 * fade)
