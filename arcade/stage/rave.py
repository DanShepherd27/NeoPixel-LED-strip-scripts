"""Fred again..-inspired look (the sparse, "desk lamp" rave lighting).

* Palette: warm practical lamps over a single saturated wash per phrase - blue,
  red, then green - and plain white for strobes. Nothing in between.
* Geometry: a few lamps at uneven, human positions, in front of a full-strip wash.
* Motion: almost none. The look starts minimal and grows: a breakdown begins with
  one lamp and adds another every four bars.
* Intensity: the wash breathes in half time (beats 1 and 3); a white strobe marks
  the start of each phrase and the drop, and nothing else.
"""

from arcade.song.effects import add, scaled
from arcade.stage.cues import PHRASE_BARS
from arcade.stage.base import WHITE, StageLook, beam, ends, fill, wash

LAMP = (255, 140, 50)
WASHES = ((0, 40, 255), (255, 0, 10), (0, 255, 40))
LAMPS = (0.14, 0.36, 0.63, 0.85)   # where the lamps stand, as a share of the strip


class RaveLook(StageLook):
    label = "Rave (Fred again..)"
    reveal_color = WHITE

    def _lamps(self, frame, count, strength):
        for position in LAMPS[:count]:
            center = position * (frame.count - 1)
            beam(frame, center, 1.0, LAMP, strength)
            add(frame, int(round(center)), scaled(LAMP, strength * 0.4))

    def _wash_color(self, cues):
        return WASHES[cues.phrase % len(WASHES)]

    def draw_breakdown(self, frame, cues, seconds):
        bar_seconds = 4.0 * cues.period
        lamps = min(len(LAMPS), 1 + int(seconds / (4.0 * bar_seconds)))
        self._lamps(frame, lamps, cues.drive(0.2, 1.0, max(cues.hit, cues.vocal)) * cues.volume)
        # A sudden hit throws a quick wash of color behind the lamps.
        fill(frame, self._wash_color(cues), 0.25 * cues.fx * (cues.hit if not cues.grid else 0.0))

    def draw_build(self, frame, cues, progress):
        # The wash creeps up from the floor under the lamps; in the last quarter the
        # lamps flicker on 8ths (small spots, not the whole strip).
        top = int(progress * 0.7 * frame.count)
        fill(frame, self._wash_color(cues), (0.1 + 0.25 * progress + 0.3 * cues.fx * cues.hit) * cues.volume, 0, top)
        strength = cues.drive(0.5, 1.0, cues.hit)
        if progress > 0.75:
            strength *= 0.3 + 0.7 * cues.ctx.subdivision_hit(2, 5.0)
        self._lamps(frame, len(LAMPS), strength)

    def draw_drop(self, frame, cues):
        color = self._wash_color(cues)
        # Beats 1 and 3 slam the wash; beats 2 and 4 only nudge it (half time).
        weight = 1.0 if cues.beat_in_bar in (0, 2) else 0.3
        fill(frame, color, cues.drive(0.08, 0.95, cues.hit * weight) * cues.volume)
        self._lamps(frame, len(LAMPS), cues.drive(0.4, 1.0, max(cues.vocal, cues.hit)))
        ends(frame, 4, WHITE, cues.snare * 0.9)
        if cues.downbeat and cues.bar_in_section % PHRASE_BARS == 0 and cues.ctx.phase < 0.08:
            wash(frame, WHITE, 0.9)   # the phrase's one strobe hit
