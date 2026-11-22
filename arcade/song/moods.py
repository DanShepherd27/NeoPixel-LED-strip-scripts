"""Calm and intimate moods: bells, verses, the whispered bridge, the outro.

Even the quiet looks keep a visible pulse: the strip is split into four
quarters and the current beat of the bar lights its quarter, so you can read
"1-2-3-4" off the strip while the music plays.
"""

import math
import random

from arcade.song.effects import (
    GOLD, GREEN, ICE, RED, SNOW, WARM, Comets, Sparkles, add, lattice, scaled, segment,
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
        if ctx.new_beat:  # a single warm bell glint marks each beat
            self.sparkles.spawn(random.randrange(frame.count), GOLD, 0.8)
        self.sparkles.draw(frame, ctx.dt, 0.6 + 0.4 * ctx.progress)


class Verse:
    """Marching dots: a lattice of lit pixels with dark gaps that steps on every
    beat; this beat's quarter of the strip flares, and a comet crosses each bar."""

    def __init__(self, colors=(RED, WARM), lively=False):
        self.colors = colors
        self.lively = lively
        self.comets = Comets()

    def render(self, frame, ctx):
        pitch, width = (4, 1) if self.lively else (6, 2)
        shift = ctx.stepped(2 if self.lively else 1) * (1 if self.lively else 2)
        voice = max(ctx.bands[2], ctx.bands[3])
        quarter = set(segment(frame, ctx.beat_in_bar))
        for index in range(frame.count):
            group = lattice(index, shift, pitch, width)
            if group is None:
                continue
            color = self.colors[group % 2]
            level = 0.22 + 0.15 * voice
            if index in quarter:  # the beat counter
                color = GOLD if ctx.is_downbeat else color
                level += 0.75 * ctx.hit
            elif ctx.is_backbeat:  # snare: every lit dot flashes, gaps stay black
                level += 0.45 * ctx.hit
                color = WARM
            if self.lively:
                level += 0.25 * ctx.offbeat_hit
            frame.pixels[index] = scaled(color, level)
        if ctx.new_bar and ctx.bar_in_section % 4 == 0:  # a comet only every fourth bar, always upward
            self.comets.launch(1, 26.0, GOLD, 9 if self.lively else 7, frame.count)
        self.comets.draw(frame, ctx.dt, 0.8 + 0.2 * ctx.level)


class Whisper:
    """The quiet "make my wish come true" moment: a few icy twinkles in the dark
    and a golden star that glows on each beat."""

    def __init__(self):
        self.phases = [random.uniform(0, math.tau) for _ in range(120)]

    def render(self, frame, ctx):
        for index in range(frame.count):
            shimmer = 0.5 + 0.5 * math.sin(ctx.t * 1.3 + self.phases[index])
            if shimmer > 0.86 and index % 3 == 0:  # roughly one lit pixel in ten
                color = blend(ICE, SNOW, shimmer)
                frame.pixels[index] = scaled(color, (shimmer - 0.86) * 5.0 * 0.5)
        star = 0.40 + 0.25 * max(ctx.bands[3], ctx.bands[4]) + 0.30 * ctx.hit
        for offset in range(5):
            if offset % 2 == 0:  # the star is dotted too: gold, dark, gold, dark, gold
                add(frame, frame.count - 1 - offset, scaled(GOLD, star))


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
        self.sparkles.draw(frame, ctx.dt, 0.3 + 0.7 * fade)
