"""Eric Prydz-inspired look (HOLO / EPIC): layered depth and slow, emotional sweeps.

* Palette: ultramarine depth, violet and magenta beams, a cool white for cores.
* Geometry: two layers - a dim drifting gradient behind, bright beams in front -
  that move at different speeds, so the strip reads as having depth (parallax).
* Motion: beams glide on long, tempo-locked cycles (two to six bars); the kick
  only lifts their brightness a little, so the movement stays smooth.
* Intensity: dark-blue floor, the white blinder kept for the drop.
"""

import math

from arcade.stage.base import WHITE, StageLook, beam, ends, glide, mirrored
from led.colors import blend

ULTRA = (10, 30, 255)
VIOLET = (120, 0, 255)
MAGENTA = (255, 0, 170)
HOLO_WHITE = (200, 220, 255)


class HoloLook(StageLook):
    label = "Holo (Eric Prydz)"
    reveal_color = HOLO_WHITE

    def _depth(self, frame, cues, strength):
        """The back layer: a blue-to-violet gradient drifting once every 16 bars,
        with a faint interlace that slides slowly, like a hologram's scan lines."""
        drift = cues.bars(16)
        for index in range(frame.count):
            position = (index / frame.count + drift) % 1.0
            color = blend(ULTRA, VIOLET, glide(position))
            interlace = 0.7 + 0.3 * math.sin(index * 2.1 - cues.beats * 0.8)
            frame.pixels[index] = tuple(int(c * strength * interlace) for c in color)

    def _beam_color(self, cues):
        return VIOLET if cues.phrase % 2 == 0 else MAGENTA

    def draw_breakdown(self, frame, cues, seconds):
        self._depth(frame, cues, 0.10 + 0.08 * cues.vocal)
        strength = 0.35 + 0.3 * cues.level
        span = frame.count - 1
        beam(frame, glide(cues.bars(4)) * span, 2.5, self._beam_color(cues), strength)
        beam(frame, (1.0 - glide(cues.bars(6))) * span, 2.0, ULTRA, strength * 0.9)

    def draw_build(self, frame, cues, progress):
        # The beams close in on the centre and narrow; the depth layer fades so the
        # eye is pulled to one point just before the drop opens everything up.
        self._depth(frame, cues, 0.10 * (1.0 - progress))
        middle = (frame.count - 1) / 2.0
        sweep = glide(cues.bars(1.0 if progress < 0.6 else 0.5))
        distance = (1.0 - progress) * middle * (0.4 + 0.6 * sweep)
        color = blend(self._beam_color(cues), HOLO_WHITE, progress * 0.7)
        mirrored(frame, distance, 2.5 - 1.5 * progress, color, 0.4 + 0.5 * progress)

    def draw_drop(self, frame, cues):
        self._depth(frame, cues, 0.12)
        middle = (frame.count - 1) / 2.0
        color = self._beam_color(cues)
        lift = 0.7 + 0.25 * cues.kick           # a gentle lift, never a strobe
        for pair in range(3):
            fan = glide(cues.bars(2) + pair / 3.0)
            distance = 3.0 + fan * (middle - 4.0)
            mirrored(frame, distance, 1.6, color, lift)
            mirrored(frame, distance, 0.0, WHITE, 0.5 * cues.downbeat)
        beam(frame, middle, 2.0, HOLO_WHITE, cues.downbeat * 0.8)
        ends(frame, 3, blend(MAGENTA, WHITE, 0.6), cues.snare)
