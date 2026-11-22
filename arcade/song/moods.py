"""Lighting moods: reusable looks the choreography assigns to song sections.

Each mood draws one frame from a :class:`BeatContext` (musical position plus
audio features). Moods keep their own small state and never touch hardware.
"""

import math
import random

from led.colors import blend, dim, hsv_to_rgb

RED = (235, 12, 28)
GREEN = (0, 200, 60)
GOLD = (255, 176, 24)
WARM = (255, 214, 150)
SNOW = (210, 230, 255)
ICE = (60, 140, 255)
WHITE_HOT = (255, 235, 200)


class BeatContext:
    """What a mood needs to know about "now"."""

    def __init__(self):
        self.t = 0.0
        self.dt = 0.0
        self.beat = 0.0          # beats since the first downbeat
        self.phase = 0.0         # 0-1 within the current beat
        self.new_beat = False
        self.new_bar = False
        self.beat_in_bar = 0
        self.bar_in_section = 0
        self.progress = 0.0      # 0-1 through the section
        self.bands = [0.0] * 6
        self.level = 0.0
        self.kick = 0.0
        self.snare = 0.0

    @property
    def pulse(self):
        """Beat envelope: 1 on the beat, decaying quickly."""
        return math.exp(-self.phase * 4.5)

    @property
    def bar_pulse(self):
        """Bar envelope: 1 on the downbeat, decaying across the bar."""
        position = (self.beat_in_bar + self.phase) / 4.0
        return math.exp(-position * 3.0)


def _scaled(color, factor):
    return dim(color, max(0.0, min(1.0, factor)))


def _add(frame, index, color):
    if 0 <= index < frame.count:
        old = frame.pixels[index]
        frame.pixels[index] = tuple(min(255, old[i] + color[i]) for i in range(3))


class Sparkles:
    """Pixels that flare then fade; shared by several moods."""

    def __init__(self, fade_per_second=2.0):
        self.fade = fade_per_second
        self.lives = {}

    def spawn(self, index, color, life=1.0):
        self.lives[index] = (color, life)

    def draw(self, frame, dt, strength=1.0):
        for index in list(self.lives):
            color, life = self.lives[index]
            _add(frame, index, _scaled(color, life * strength))
            life -= dt * self.fade
            if life <= 0:
                del self.lives[index]
            else:
                self.lives[index] = (color, life)


class Comets:
    """Bright heads with fading tails that cross the strip."""

    def __init__(self):
        self.items = []  # [position, direction, speed, color, tail]

    def launch(self, direction, speed, color, tail=8, count=60):
        start = 0.0 if direction > 0 else count - 1.0
        self.items.append([start, direction, speed, color, tail])

    def draw(self, frame, dt, strength=1.0):
        for comet in list(self.items):
            comet[0] += comet[1] * comet[2] * dt
            if not -comet[4] <= comet[0] <= frame.count + comet[4]:
                self.items.remove(comet)
                continue
            for step in range(comet[4]):
                level = (1.0 - step / comet[4]) ** 2
                _add(frame, int(round(comet[0] - comet[1] * step)),
                     _scaled(comet[3], level * strength))


class Bells:
    """Intro: sparse sleigh-bell glints that grow as the song wakes up."""

    def __init__(self):
        self.sparkles = Sparkles(1.6)

    def render(self, frame, ctx):
        rate = (1.5 + 18.0 * ctx.bands[4] + 14.0 * ctx.bands[5]) * (0.3 + ctx.progress)
        if random.random() < rate * ctx.dt:
            self.sparkles.spawn(random.randrange(frame.count),
                                random.choice((WARM, GOLD, SNOW)))
        glow = 0.04 + 0.12 * ctx.progress
        for index in range(frame.count):
            frame.pixels[index] = _scaled(GOLD, glow * (0.6 + 0.4 * ctx.pulse))
        self.sparkles.draw(frame, ctx.dt, 0.5 + 0.5 * ctx.progress)


class Verse:
    """Warm, intimate candy stripes that breathe with a comet each bar."""

    def __init__(self, colors=(RED, WARM), lively=False):
        self.colors = colors
        self.lively = lively
        self.comets = Comets()
        self.shift = 0.0

    def render(self, frame, ctx):
        speed = (3.0 + 7.0 * ctx.progress) if self.lively else 2.0
        self.shift += speed * ctx.dt
        voice = max(ctx.bands[2], ctx.bands[3])
        base = 0.20 + 0.16 * voice + 0.22 * ctx.pulse * (0.7 if self.lively else 0.45)
        for index in range(frame.count):
            stripe = int((index + self.shift) // 6) % 2
            frame.pixels[index] = _scaled(self.colors[stripe], base)
        if ctx.new_bar or (self.lively and ctx.new_beat and ctx.beat_in_bar == 2):
            direction = 1 if (ctx.bar_in_section + ctx.beat_in_bar) % 2 == 0 else -1
            self.comets.launch(direction, 38.0, GOLD, 9 if self.lively else 7, frame.count)
        self.comets.draw(frame, ctx.dt, 0.8 + 0.2 * ctx.level)


class Whisper:
    """The quiet "make my wish come true" moment: icy shimmer and a star."""

    def __init__(self):
        self.phases = [random.uniform(0, math.tau) for _ in range(120)]

    def render(self, frame, ctx):
        breathe = 0.55 + 0.45 * math.sin((ctx.beat / 4.0) * math.pi - math.pi / 2)
        for index in range(frame.count):
            shimmer = 0.5 + 0.5 * math.sin(ctx.t * 1.7 + self.phases[index])
            color = blend(ICE, SNOW, shimmer * 0.6)
            frame.pixels[index] = _scaled(color, 0.03 + 0.12 * shimmer * breathe)
        star = 0.55 + 0.35 * max(ctx.bands[3], ctx.bands[4]) + 0.1 * breathe
        for offset in range(5):
            _add(frame, frame.count - 1 - offset, _scaled(GOLD, star * (1 - offset * 0.18)))


class Build:
    """Two-bar riser: a column of light climbs and heats toward the chorus."""

    def render(self, frame, ctx):
        p = ctx.progress
        height = (p ** 1.4) * frame.count
        flicker = 0.75 + 0.25 * ctx.pulse
        for index in range(int(height) + 1):
            heat = index / max(1.0, frame.count - 1)
            color = blend(blend(ICE, GOLD, min(1.0, heat * 1.6)), WHITE_HOT, max(0.0, p - 0.7) * 3.3)
            frame.pixels[index] = _scaled(color, flicker * (0.4 + 0.6 * p))
        if p > 0.55:
            for _ in range(int(2 + 10 * p)):
                _add(frame, random.randrange(frame.count), _scaled(WHITE_HOT, 0.3 + 0.5 * p))


class Chorus:
    """Celebration: kick-pumped red/green/white chase that changes each bar."""

    def __init__(self, colors=(RED, GREEN, WARM), accent=GOLD, power=1.0):
        self.colors = colors
        self.accent = accent
        self.power = power
        self.sparkles = Sparkles(3.0)
        self.burst = 0.0

    def render(self, frame, ctx):
        phrase = ctx.bar_in_section % 4
        count = frame.count
        if phrase == 0 and ctx.new_bar:
            self.burst = 1.0
        self.burst = max(0.0, self.burst - ctx.dt * 5.0)
        drive = min(1.0, 0.35 + 0.45 * ctx.pulse + 0.4 * ctx.kick + 0.2 * ctx.level) * self.power
        drive = min(1.0, drive)
        pace = 2.2 * ctx.beat
        for index in range(count):
            if phrase == 0:
                slot = index + pace
            elif phrase == 1:
                slot = index - pace
            elif phrase == 2:
                slot = abs(index - (count - 1) / 2.0) * 1.0 + pace
            else:
                slot = index * 1.0 + 15 * math.sin(ctx.beat * math.pi / 2)
            color = self.colors[int(slot // 5) % len(self.colors)]
            frame.pixels[index] = _scaled(color, drive)
        if self.burst > 0:
            for index in range(count):
                if random.random() < 0.55 * self.burst:
                    frame.pixels[index] = _scaled(self.accent, 0.7 + 0.3 * self.burst)
        if ctx.snare > 0.5 and random.random() < 0.9:
            for _ in range(4):
                self.sparkles.spawn(random.randrange(count), WARM, 0.9)
        self.sparkles.draw(frame, ctx.dt, 0.9)


class Dream:
    """Bridge: slow aurora of teal, violet and pink that follows the spectrum."""

    def __init__(self):
        self.smooth = [0.0] * 6

    def render(self, frame, ctx):
        for band in range(6):
            self.smooth[band] += (ctx.bands[band] - self.smooth[band]) * min(1.0, ctx.dt * 6)
        for index in range(frame.count):
            wave = 0.5 + 0.5 * math.sin(index * 0.13 + ctx.t * 0.9)
            hue = 175.0 + 125.0 * wave + 40.0 * ctx.kick
            band = self.smooth[min(5, index * 6 // frame.count)]
            value = 0.12 + 0.55 * band + 0.3 * ctx.pulse * wave
            frame.pixels[index] = hsv_to_rgb(hue, 0.95, min(1.0, value))


class Finale:
    """Peak joy: spectrum meter in holiday colors with firework bursts."""

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
                glow = 0.85 if offset < lit else 0.12
                frame.pixels[band * size + offset] = _scaled(self.SEGMENTS[band], glow)
        if ctx.new_beat:
            big = ctx.beat_in_bar == 0
            color = GOLD if big else random.choice((RED, GREEN, WARM, SNOW))
            self.bursts.append([random.uniform(8, count - 8), 0.0, color, 1.0 if big else 0.8])
        for burst in list(self.bursts):
            burst[1] += (48.0 if burst[3] > 0.9 else 34.0) * ctx.dt
            burst[3] -= ctx.dt * 1.7
            if burst[3] <= 0:
                self.bursts.remove(burst)
                continue
            for side in (-1, 1):
                for thickness in range(3):
                    _add(frame, int(burst[0] + side * (burst[1] - thickness)),
                         _scaled(burst[2], burst[3] * (1 - thickness * 0.3)))


class Afterglow:
    """Outro: warm twinkles that fade out with the music."""

    def __init__(self):
        self.sparkles = Sparkles(0.9)

    def render(self, frame, ctx):
        fade = min(1.0, ctx.level / 0.5)
        if random.random() < (3 + 10 * fade) * ctx.dt:
            self.sparkles.spawn(random.randrange(frame.count), random.choice((WARM, GOLD, RED, GREEN)))
        for index in range(frame.count):
            frame.pixels[index] = _scaled(GOLD, 0.05 * fade)
        self.sparkles.draw(frame, ctx.dt, 0.3 + 0.7 * fade)


def build_moods():
    return {
        "bells": Bells(),
        "verse": Verse(),
        "verse_green": Verse(colors=(GREEN, WARM)),
        "rising": Verse(colors=(RED, GOLD), lively=True),
        "whisper": Whisper(),
        "build": Build(),
        "chorus": Chorus(),
        "chorus_gold": Chorus(colors=(RED, GOLD, GREEN, WARM), accent=WARM, power=1.0),
        "dream": Dream(),
        "finale": Finale(),
        "afterglow": Afterglow(),
    }
