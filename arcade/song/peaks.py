"""High-energy moods: build-ups, choruses, the bridge and the finale.

Every beat is a visible event: the strip pops on the beat and falls back to
a dark floor before the next one, the chase jumps one block per beat, beat 1
carries a gold accent and the snare (beats 2 and 4) a white-warm flash.
"""

import math
import random

from arcade.song.effects import (
    GOLD, GREEN, ICE, RED, SNOW, WARM, WHITE_HOT, Sparkles, add, add_all, scaled,
)
from arcade.song.rhythm import ease_out
from led.colors import blend, hsv_to_rgb


class Build:
    """Two-bar riser: a column climbs one step per beat, then speeds up to 8ths
    and 16ths, and goes dark for a breath right before the chorus lands."""

    def render(self, frame, ctx):
        p = ctx.progress
        rate = 1 if p < 0.5 else (2 if p < 0.875 else 4)
        beats_in = p * 8.0  # the build-up is exactly two bars
        whole = math.floor(beats_in)
        climbed = (whole + ease_out((beats_in - whole) / 0.3)) / 8.0
        height = min(1.0, climbed) ** 1.2 * (frame.count - 1)
        flash = ctx.subdivision_hit(rate, 6.0)
        for index in range(int(height) + 1):
            heat = index / max(1.0, frame.count - 1)
            color = blend(blend(ICE, GOLD, min(1.0, heat * 1.6)), WHITE_HOT, max(0.0, p - 0.7) * 3.3)
            frame.pixels[index] = scaled(color, 0.25 + 0.75 * flash * (0.5 + 0.5 * p))
        if p > 0.5:
            for _ in range(int(2 + 10 * p)):
                add(frame, random.randrange(frame.count), scaled(WHITE_HOT, 0.4 * flash))
        if p > 0.96:  # the breath of silence before the drop
            frame.pixels = [(0, 0, 0)] * frame.count


class Chorus:
    """Celebration locked to the drums: block-per-beat chase, pop on every beat,
    gold downbeat, white snare on 2 and 4, sparkling off-beats."""

    def __init__(self, colors=(RED, GREEN, WARM), accent=GOLD):
        self.colors = colors
        self.accent = accent
        self.sparkles = Sparkles(4.0)

    def render(self, frame, ctx):
        count = frame.count
        phrase = ctx.bar_in_section % 4
        steps = ctx.stepped(1.0) * 5.0
        pop = 0.26 + 0.74 * ctx.hit
        for index in range(count):
            if phrase == 0:
                slot = index + steps
            elif phrase == 1:
                slot = index - steps
            elif phrase == 2:
                slot = abs(index - (count - 1) / 2.0) + steps
            else:
                slot = index + 15 * math.sin(ctx.beat * math.pi / 2.0)
            color = self.colors[int(slot // 5) % len(self.colors)]
            frame.pixels[index] = scaled(color, pop)
        if ctx.is_downbeat:
            add_all(frame, scaled(self.accent, 0.55 * ctx.hit))
            if phrase == 0:  # every fourth bar: a glittering burst
                for index in range(count):
                    if random.random() < 0.5 * ctx.hit:
                        add(frame, index, scaled(WARM, 0.8))
        elif ctx.is_backbeat:
            side = ctx.beat_in_bar // 2  # beat 2 floods from the bottom, beat 4 from the top
            for index in range(count):
                reach = (index if side == 0 else count - 1 - index) / count
                add(frame, index, scaled(WHITE_HOT, max(0.0, 1.0 - reach * 2.2) * 0.7 * ctx.hit))
        if ctx.new_eighth and not ctx.new_beat and random.random() < 0.7:
            for _ in range(3):
                self.sparkles.spawn(random.randrange(count), WARM, 0.9)
        if phrase == 3 and ctx.beat_in_bar == 3:  # fill into the next phrase: 8th flashes
            add_all(frame, scaled(self.accent, 0.3 * ctx.subdivision_hit(2, 9.0)))
        self.sparkles.draw(frame, ctx.dt, 0.9)


class Dream:
    """Bridge: aurora of teal, violet and pink that breathes on every beat."""

    def __init__(self):
        self.smooth = [0.0] * 6

    def render(self, frame, ctx):
        for band in range(6):
            self.smooth[band] += (ctx.bands[band] - self.smooth[band]) * min(1.0, ctx.dt * 8)
        drift = ctx.stepped(1.0, 0.5) * 0.35
        for index in range(frame.count):
            wave = 0.5 + 0.5 * math.sin(index * 0.13 + drift)
            hue = 175.0 + 125.0 * wave + 50.0 * ctx.hit
            band = self.smooth[min(5, index * 6 // frame.count)]
            value = 0.10 + 0.30 * band + 0.55 * ctx.hit * (0.5 + 0.5 * wave)
            frame.pixels[index] = hsv_to_rgb(hue, 0.95, min(1.0, value))
        if ctx.is_backbeat:
            add_all(frame, scaled(SNOW, 0.12 * ctx.hit))


class Finale:
    """Peak joy: spectrum meter in holiday colors with a firework on every beat."""

    SEGMENTS = (RED, GOLD, GREEN, WARM, RED, GREEN)

    def __init__(self):
        self.bursts = []  # [center, radius, color, life]
        self.smooth = [0.0] * 6

    def render(self, frame, ctx):
        count = frame.count
        size = count // 6
        for band in range(6):
            self.smooth[band] += (ctx.bands[band] - self.smooth[band]) * min(1.0, ctx.dt * 14)
            lit = int(round(self.smooth[band] * size))
            for offset in range(size):
                glow = 0.30 + 0.55 * ctx.hit if offset < lit else 0.05 + 0.10 * ctx.hit
                frame.pixels[band * size + offset] = scaled(self.SEGMENTS[band], glow)
        if ctx.new_beat:
            if ctx.is_downbeat:
                self.bursts.append([random.uniform(10, count - 10), 0.0, GOLD, 1.0])
            elif ctx.is_backbeat:
                self.bursts.append([2.0, 0.0, WHITE_HOT, 0.8])
                self.bursts.append([count - 3.0, 0.0, WHITE_HOT, 0.8])
            else:
                color = random.choice((RED, GREEN, SNOW))
                self.bursts.append([random.uniform(8, count - 8), 0.0, color, 0.8])
        for burst in list(self.bursts):
            burst[1] += (52.0 if burst[3] > 0.9 else 38.0) * ctx.dt
            burst[3] -= ctx.dt * 2.0
            if burst[3] <= 0:
                self.bursts.remove(burst)
                continue
            for side in (-1, 1):
                for thickness in range(3):
                    add(frame, int(burst[0] + side * (burst[1] - thickness)),
                        scaled(burst[2], burst[3] * (1 - thickness * 0.3)))
