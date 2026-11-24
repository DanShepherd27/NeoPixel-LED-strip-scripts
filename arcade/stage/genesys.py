"""Anyma-inspired look (the "Genesys" shows): a cold, cinematic machine.

* Palette: a black void, deep-blue haze, ice-cyan and chrome-white lines. Every
  fourth phrase turns the lines crimson - the one warm, "human" color.
* Geometry: a thin spine and laser-thin lines, symmetric about the centre.
* Motion: slow and mechanical in breakdowns (one scan per two bars); in the drop
  the lines do not move at all - a fixed laser fan where each kick flares one rung.
* Intensity: mostly dark, with white kept for line cores and the drop reveal.
"""

from arcade.song.effects import add, scaled
from arcade.stage.base import WHITE, StageLook, beam, ends, fill, glide, mirrored
from led.colors import blend

ICE = (120, 215, 255)
CHROME = (225, 240, 255)
ABYSS = (0, 16, 110)
CRIMSON = (255, 0, 20)
FAN = (4.5, 10.5, 17.5, 24.5)   # distance of each beat's laser rung from the centre


class GenesysLook(StageLook):
    label = "Genesys (Anyma)"
    reveal_color = CHROME

    def _line_color(self, cues):
        if cues.phrase % 4 == 3:
            return CRIMSON
        return ICE if cues.phrase % 2 == 0 else CHROME

    def _haze(self, frame, cues, strength):
        """Volumetric haze: the deep blue swells once per bar, rising toward the top."""
        swell = 0.6 + 0.4 * glide(cues.bars(1))
        for index in range(frame.count):
            height = index / max(1, frame.count - 1)
            add(frame, index, scaled(ABYSS, strength * swell * (0.5 + 0.5 * height)))

    def _scan(self, frame, position, color, strength, trail=5, direction=1):
        """A thin scan line with a short trail behind it."""
        head = position * (frame.count - 1)
        beam(frame, head, 0.6, color, strength)
        add(frame, int(round(head)), scaled(WHITE, strength * 0.5))
        for step in range(1, trail):
            beam(frame, head - direction * step, 0.5, color, strength * 0.45 * (1 - step / trail))

    def draw_breakdown(self, frame, cues, seconds):
        # The haze breathes with the music and flashes on a sudden hit; the scan line
        # glows with the volume and pops on every beat.
        self._haze(frame, cues, (0.08 + 0.25 * cues.vocal + 0.45 * cues.fx * cues.hit) * cues.volume)
        position = cues.bars(4)                      # up over two bars, down over two
        rising = position < 0.5
        self._scan(frame, glide(position), self._line_color(cues),
                   cues.drive(0.35, 1.0, cues.hit) * cues.volume,
                   trail=4 + int(6 * cues.energy), direction=1 if rising else -1)

    def draw_build(self, frame, cues, progress):
        # The haze thickens and whitens; the scan doubles its rate twice and splits
        # into two mirrored lines, so the tension is in speed, not in flashing.
        self._haze(frame, cues, (0.12 + 0.3 * progress + 0.3 * cues.fx * cues.hit) * cues.volume)
        bars_per_sweep = 1.0 if progress < 0.5 else (0.5 if progress < 0.85 else 0.25)
        sweep = glide(cues.bars(bars_per_sweep))
        color = blend(ICE, CHROME, progress)
        middle = (frame.count - 1) / 2.0
        strength = cues.drive(0.3 + 0.4 * progress, 1.0, cues.hit)
        mirrored(frame, sweep * middle, 0.6 + 0.8 * cues.hit * cues.fx, color, strength)
        if progress > 0.5:
            fill(frame, scaled(CHROME, 0.08 * progress), 1.0)

    def draw_drop(self, frame, cues):
        color = self._line_color(cues)
        # The haze thumps with the kick; the whole fan flickers on each hit and the
        # current beat's rung flares wide with a white core.
        self._haze(frame, cues, (0.06 + 0.12 * cues.vocal + 0.35 * cues.fx * cues.kick) * cues.volume)
        skeleton = cues.drive(0.1, 0.45, cues.hit) * cues.volume
        for rung, distance in enumerate(FAN):
            flare = cues.hit if rung == cues.beat_in_bar else 0.0
            width = 0.5 + 1.2 * flare * cues.fx
            mirrored(frame, distance, width, color, max(skeleton, cues.drive(0.1, 1.0, flare)))
            if flare > 0.3:
                mirrored(frame, distance, 0.0, WHITE, min(1.0, flare * 0.8 * cues.fx))
        middle = (frame.count - 1) / 2.0
        beam(frame, middle, 1.5 + 1.5 * cues.fx, WHITE, cues.downbeat)  # the core ignites on beat 1
        ends(frame, 3, CHROME, cues.snare)
