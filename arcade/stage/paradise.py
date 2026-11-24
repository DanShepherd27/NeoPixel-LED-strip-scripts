"""Swedish House Mafia-inspired look (the "Paradise Again" ring): lights, no video.

* Palette: one color per phrase - red, then warm white - with an amber blinder.
* Geometry: the ring seen edge-on - six truss blocks with dark gaps, lit in
  mirrored pairs (outer, middle, inner), so everything is symmetric.
* Motion: the kick steps the lit pair around the ring; beat 1 fires the whole
  ring at once. In breakdowns one pair circles slowly, once per bar.
* Intensity: the ring always glows faintly so the structure is visible; the
  big moments are whole-ring hits, never more than one per bar.
"""

from arcade.stage.base import WHITE, StageLook, ends, fill
from led.colors import blend

RED = (255, 0, 0)
WARM_WHITE = (255, 225, 190)
AMBER = (255, 120, 20)
BLOCKS = 6
GAP = 3
PAIRS = ((0, 5), (1, 4), (2, 3))     # outer, middle, inner
STEP = (0, 1, 2, 1)                  # which pair each beat of the bar lights


class ParadiseLook(StageLook):
    label = "Paradise (Swedish House Mafia)"
    reveal_color = AMBER

    def _color(self, cues):
        return RED if cues.phrase % 2 == 0 else WARM_WHITE

    def _block(self, frame, block, color, strength):
        size = frame.count // BLOCKS
        fill(frame, color, strength, block * size + GAP // 2, (block + 1) * size - (GAP - GAP // 2))

    def _pair(self, frame, pair, color, strength):
        for block in PAIRS[pair]:
            self._block(frame, block, color, strength)

    def _ring(self, frame, color, strength):
        for block in range(BLOCKS):
            self._block(frame, block, color, strength)

    def draw_breakdown(self, frame, cues, seconds):
        # Warm, euphoric: the ring glows amber and one pair circles once per bar,
        # cross-fading so the rotation has no hard edges.
        self._ring(frame, AMBER, (0.05 + 0.12 * cues.vocal + 0.4 * cues.fx * cues.hit) * cues.volume)
        position = cues.bars(1) * len(STEP)
        current = int(position) % len(STEP)
        mix = position - int(position)
        strength = cues.drive(0.3, 1.0, max(cues.hit, 0.5 * cues.vocal)) * cues.volume
        self._pair(frame, STEP[current], WARM_WHITE, strength * (1.0 - mix))
        self._pair(frame, STEP[(current + 1) % len(STEP)], WARM_WHITE, strength * mix)

    def draw_build(self, frame, cues, progress):
        # The ring fills from the outside in, one pair per third of the build; in the
        # second half the newest pair blinks on 8th notes (one pair, a small area).
        lit = min(len(PAIRS), 1 + int(progress * len(PAIRS)))
        ctx = cues.ctx
        for pair in range(lit):
            strength = cues.drive(0.2 + 0.45 * progress, 1.0, cues.hit) * cues.volume
            if pair == lit - 1 and progress > 0.5:
                strength *= 0.4 + 0.6 * ctx.subdivision_hit(2, 6.0)
            self._pair(frame, pair, blend(AMBER, WHITE, progress), strength)

    def draw_drop(self, frame, cues):
        color = self._color(cues)
        self._ring(frame, color, (0.06 + 0.1 * cues.energy) * cues.volume)
        if cues.downbeat > 0.0:
            self._ring(frame, color, min(1.0, 0.7 + 0.3 * cues.fx) * cues.downbeat)
        else:
            self._pair(frame, STEP[cues.beat_in_bar], color, cues.drive(0.15, 1.0, cues.hit))
            # Loud hits spill onto the neighbouring pair, so big moments light more ring.
            spill = STEP[(cues.beat_in_bar + 1) % len(STEP)]
            self._pair(frame, spill, color, 0.5 * cues.fx * cues.hit * cues.energy)
        ends(frame, 3, WHITE if color == RED else AMBER, cues.snare)
