"""High-energy moods: build-ups, choruses, the bridge and the finale.

Every beat is a visible event: the strip pops on the beat and falls back to
a dark floor before the next one, the chase jumps one block per beat, beat 1
carries a gold accent and the snare (beats 2 and 4) a white-warm flash.
"""

import math
import random

from arcade.song.effects import (
    GOLD, GREEN, ICE, RED, SNOW, WARM, WHITE_HOT, Sparkles, add, lattice, scaled,
)
from arcade.song.rhythm import ease_out
from led.colors import blend, hsv_to_rgb


BLUE = (20, 90, 255)


class Build:
    """Two-bar riser: a dotted column climbs one step per beat, its gaps closing
    from every third pixel to every other one as it speeds up to 8ths and 16ths,
    then it goes dark for a breath right before the chorus lands.

    ``palette="ice"`` is the pure blue riser out of the whisper; ``"gold"`` heats
    from ice through gold to white and adds sparks (used before the final chorus).
    """

    def __init__(self, palette="ice"):
        self.palette = palette

    def _color(self, heat, p):
        if self.palette == "gold":
            return blend(blend(ICE, GOLD, min(1.0, heat * 1.6)), WHITE_HOT, max(0.0, p - 0.7) * 3.3)
        # Stays blue the whole way up; only the last moments whiten toward the drop.
        return blend(blend(BLUE, ICE, min(1.0, heat * 1.4)), SNOW, max(0.0, p - 0.85) * 5.0)

    def render(self, frame, ctx):
        p = ctx.progress
        rate = 1 if p < 0.5 else (2 if p < 0.875 else 4)
        beats_in = p * 8.0  # the build-up is exactly two bars
        whole = math.floor(beats_in)
        climbed = (whole + ease_out((beats_in - whole) / 0.12)) / 8.0
        height = min(1.0, climbed) ** 1.2 * (frame.count - 1)
        flash = ctx.subdivision_hit(rate, 6.0)
        pitch = 3 if p < 0.6 else 2
        for index in range(int(height) + 1):
            if index % pitch:
                continue
            heat = index / max(1.0, frame.count - 1)
            frame.pixels[index] = scaled(self._color(heat, p), 0.35 + 0.65 * flash)
        if self.palette == "gold" and p > 0.5:
            for _ in range(int(1 + 5 * p)):
                add(frame, random.randrange(frame.count), scaled(WHITE_HOT, 0.6 * flash))
        if p > 0.96:  # the breath of silence before the drop
            frame.pixels = [(0, 0, 0)] * frame.count


class Chorus:
    """Celebration locked to the drums, drawn as dots in the dark. A lattice of
    lit groups steps one group per beat, always drifting the same way so the eye
    never has to reverse; the pop, the gold downbeat core and the snare flashes
    are static, so the beat is felt without fast runs along the strip."""

    def __init__(self, colors=(RED, GREEN, WARM), accent=GOLD):
        self.colors = colors
        self.accent = accent
        self.sparkles = Sparkles(4.0)

    def render(self, frame, ctx):
        count = frame.count
        phrase = ctx.bar_in_section % 4
        pitch, width = (4, 2) if phrase == 2 else (6, 3)
        steps = ctx.stepped(1.0) * 3.0
        pop = 0.30 + 0.70 * ctx.hit
        for index in range(count):
            group = lattice(index, steps, pitch, width)
            if group is None:
                continue
            color = self.colors[group % len(self.colors)]
            if ctx.is_downbeat and (int(index + steps) % pitch) == width // 2:
                color = self.accent  # gold core in every group on the downbeat
            frame.pixels[index] = scaled(color, pop)
        if ctx.is_backbeat:  # snare: white dots flash in place, alternating positions
            for index in range(ctx.beat_in_bar // 2 * 6, count, 12):
                add(frame, index, scaled(WHITE_HOT, 0.9 * ctx.hit))
        if ctx.is_downbeat and phrase == 0:  # every fourth bar: sparse glitter burst
            for index in range(count):
                if random.random() < 0.12 * ctx.hit:
                    add(frame, index, scaled(WARM, 0.9))
        if ctx.new_eighth and not ctx.new_beat and random.random() < 0.7:
            for _ in range(3):
                self.sparkles.spawn(random.randrange(count), WARM, 0.9)
        self.sparkles.draw(frame, ctx.dt, 0.9)


class Dream:
    """Bridge: aurora of teal, violet and pink that breathes on every beat."""

    def __init__(self):
        self.smooth = [0.0] * 6

    def render(self, frame, ctx):
        for band in range(6):
            self.smooth[band] += (ctx.bands[band] - self.smooth[band]) * min(1.0, ctx.dt * 8)
        drift = ctx.stepped(1.0, 0.15) * 0.45
        for index in range(frame.count):
            wave = 0.5 + 0.5 * math.sin(index * 0.13 + drift)
            hue = 175.0 + 125.0 * wave + 50.0 * ctx.hit
            band = self.smooth[min(5, index * 6 // frame.count)]
            if wave < 0.45:  # troughs of the wave stay black, leaving drifting ribbons
                continue
            edge = (wave - 0.45) / 0.55
            value = (0.15 + 0.30 * band + 0.55 * ctx.hit) * edge
            frame.pixels[index] = hsv_to_rgb(hue, 0.95, min(1.0, value))


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
            for offset in range(0, min(lit, size), 2):  # every other pixel: dotted bars
                frame.pixels[band * size + offset] = scaled(
                    self.SEGMENTS[band], 0.35 + 0.55 * ctx.hit)
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
