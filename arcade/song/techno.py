"""Club look patterns: red, black and white only, built for readability.

Every visual element stands for one sound and keeps that meaning for the whole song:

* **kick** - a wave from the centre that reaches the ends exactly as the next kick lands;
* **snare** (beats 2 and 4) - the blocks at both ends flash once, in place;
* **acid bassline / lead** - a bar whose height follows the sound's brightness;
* **phrase start** (every 8 bars) - the only full-strip flash;
* **phrase fill** (last two beats of a phrase) - rounds fired from both ends to the centre.

Behind that, a slow dotted field shows the section's energy. Nothing is random, so every
bar of a phrase looks the same, and full-strip flashes stay far below 3 per second.
"""

import math

from arcade.song.effects import add, scaled

RED = (255, 0, 0)
BLOOD = (170, 0, 0)
HOT = (255, 80, 80)      # a pinkish "hot" red for heads and cores
WHITE = (255, 255, 255)  # only for the first downbeat of a section
PHRASE_BARS = 8
END_BLOCK = 7            # pixels lit at each end for the snare
FILL_BEATS = 2           # the fill takes the last two beats of a phrase


def _middle(frame):
    return (frame.count - 1) / 2.0


def _quantize(value, step):
    return int(value // step * step)


def _phrase_bar(ctx):
    return ctx.bar_in_section % PHRASE_BARS


def _in_fill(ctx):
    return _phrase_bar(ctx) == PHRASE_BARS - 1 and ctx.beat_in_bar >= 4 - FILL_BEATS


def _end_blocks(frame, level, color=RED):
    for index in list(range(END_BLOCK)) + list(range(frame.count - END_BLOCK, frame.count)):
        add(frame, index, scaled(color, level))


class Field:
    """Background: every third pixel glows dark red at the section's energy; with
    ``breathe`` it swells once per bar instead of holding still."""

    def __init__(self, level=0.15, breathe=False):
        self.level, self.breathe = float(level), bool(breathe)

    def render(self, frame, ctx):
        level = self.level
        if self.breathe:
            level *= 0.35 + 0.65 * (0.5 - 0.5 * math.cos(2 * math.pi * ctx.bar_position))
        for index in range(1, frame.count, 3):
            add(frame, index, scaled(BLOOD, level))


class Pulse:
    """The kick: each beat a wave leaves the centre and reaches the ends just as the
    next beat lands, so its speed *is* the tempo. The downbeat wave is a thick red band;
    the others are thin and hot red."""

    def __init__(self, gain=1.0, heavy=False):
        self.gain, self.heavy = float(gain), bool(heavy)

    def render(self, frame, ctx):
        middle = _middle(frame)
        half = middle + 1.0
        front = _quantize(ctx.phase * half, 2)
        fade = 1.0 if ctx.phase < 0.8 else (1.0 - ctx.phase) / 0.2
        thick = ctx.is_downbeat or self.heavy
        color = RED if ctx.is_downbeat else HOT
        for side in (-1, 1):
            head = int(round(middle + side * (front + 0.5)))
            add(frame, head, scaled(color, self.gain * fade))
            if thick:
                add(frame, head - side, scaled(RED, 0.8 * self.gain * fade))
            for step in range(1, 4):
                add(frame, head - side * (step + 1), scaled(BLOOD, 0.4 * (1 - step / 4) * self.gain * fade))
        if ctx.phase < 0.12:   # the strike at the centre
            for offset in (0, 1):
                add(frame, int(middle) + offset, scaled(color, self.gain))


class Accents:
    """Snare, phrase start and phrase fill. Snare: the end blocks flash once on beats
    2 and 4. Phrase start: one full-strip flash (white when a section begins). Fill: in
    the last two beats of a phrase, rounds are fired from both ends to the centre on 8ths."""

    def render(self, frame, ctx):
        bar = _phrase_bar(ctx)
        if bar == 0 and ctx.is_downbeat and ctx.phase < 0.12:
            color = WHITE if ctx.bar_in_section == 0 else RED
            frame.pixels = [scaled(color, 1.0)] * frame.count
            return
        if ctx.is_backbeat and ctx.phase < 0.22:
            _end_blocks(frame, 1.0)
        if _in_fill(ctx):
            middle = _middle(frame)
            travel = _quantize(((ctx.beat * 2) % 1.0) * middle, 2)
            for side in (-1, 1):
                head = int(round(middle - side * (middle - travel)))
                add(frame, head, scaled(HOT, 1.0))
                for step in range(1, 4):
                    add(frame, head + side * step, scaled(RED, 0.7 * (1 - step / 4)))


class Countdown:
    """Build-up: a dotted column climbs one step per beat; in the last bar the snare
    blocks flash on every beat; the final half beat is dark, then the drop lands."""

    def __init__(self, beats=16):
        self.beats = max(4, int(beats))

    def render(self, frame, ctx):
        elapsed = ctx.progress * self.beats
        if elapsed > self.beats - 0.5:
            return
        height = int(math.floor(elapsed) + 1) / self.beats * (frame.count - 1)
        top = int(height)
        for index in range(0, top + 1, 2):
            add(frame, index, scaled(RED, 0.35 + 0.5 * index / frame.count))
        add(frame, top - top % 2, scaled(HOT, 1.0))
        if elapsed >= self.beats - 4 and ctx.phase < 0.22:
            _end_blocks(frame, 0.9)


class Shutdown:
    """Outro: the dotted field shrinks toward the centre one step per bar, the kick
    keeps beating at the centre, and the last bar is one pixel blinking on the beat."""

    def __init__(self, bars=8):
        self.bars = max(1, int(bars))

    def render(self, frame, ctx):
        middle = int(_middle(frame))
        bars_left = self.bars - math.floor(ctx.progress * self.bars)
        if bars_left <= 1:
            if ctx.phase < 0.5:
                add(frame, middle, scaled(RED, 0.9))
            return
        reach = int(bars_left / self.bars * (frame.count / 2))
        for offset in range(-reach, reach + 1, 3):
            add(frame, middle + offset, scaled(BLOOD, 0.35))
        for offset in (0, 1):
            add(frame, middle + offset, scaled(RED, 0.3 + 0.7 * ctx.hit))


class Lead:
    """The acid bassline or lead instrument: a bar whose height follows the sound's
    brightness (the filter sweep or pitch). It listens to the 300 Hz - 5 kHz bands,
    turns on and off with hysteresis so it does not flicker, moves in 3-pixel steps,
    and leaves a short fading mark wherever it has just been."""

    ON, OFF = 0.5, 0.38

    def __init__(self, color=RED, core=HOT, gain=1.0):
        self.color, self.core, self.gain = color, core, float(gain)
        self.peak = 0.08
        self.low, self.high = 0.3, 0.7      # running range of the brightness, to fill the strip
        self.position = 0.5
        self.active = False
        self.marks = {}                      # pixel -> remaining glow

    def render(self, frame, ctx):
        low_mid, mid, high_mid = ctx.bands[2], ctx.bands[3], ctx.bands[4]
        energy = 0.3 * low_mid + 0.5 * mid + 0.4 * high_mid
        self.peak = max(0.08, energy, self.peak * (1.0 - ctx.dt * 0.08))
        level = energy / self.peak
        self.active = level >= (self.OFF if self.active else self.ON)
        for index in list(self.marks):
            add(frame, index, scaled(self.color, self.marks[index] * 0.5 * self.gain))
            self.marks[index] -= ctx.dt * 2.5
            if self.marks[index] <= 0:
                del self.marks[index]
        if not self.active:
            return
        weight = low_mid + mid + high_mid + 1e-6
        brightness = (0.1 * low_mid + 0.5 * mid + 0.9 * high_mid) / weight
        self.low = min(brightness, self.low + ctx.dt * 0.03)    # range creeps inward slowly
        self.high = max(brightness, self.high - ctx.dt * 0.03)
        span = max(0.12, self.high - self.low)
        target = max(0.0, min(1.0, (brightness - self.low) / span))
        self.position += (target - self.position) * min(1.0, ctx.dt * 8.0)
        index = _quantize(self.position * (frame.count - 4), 3) + 1
        strength = min(1.0, level) * self.gain
        for offset in (-1, 1):
            add(frame, index + offset, scaled(self.color, strength * 0.55))
        add(frame, index, scaled(self.core, strength))
        self.marks[index] = 1.0
