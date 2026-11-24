"""The stage-look interface and the drawing primitives the looks share.

A look is a lighting designer's style for one artist: its palette, geometry and how
it moves in each section. Subclasses draw the three sections; the base class tracks
the arrangement, keeps the breath of darkness before a drop, and lands the drop
with one reveal flash.
"""

import math
from abc import ABC, abstractmethod

from arcade.song.effects import add, scaled
from arcade.stage.cues import Arrangement, StageCues
from led.colors import blend

WHITE = (255, 255, 255)


class StageLook(ABC):
    """``render(frame, ctx)`` like every song pattern; usable live and in song shows."""

    label = ""
    reveal_color = WHITE

    def __init__(self, section=None):
        self.arrangement = Arrangement(section)

    def render(self, frame, ctx):
        cues = StageCues(ctx)
        arrangement = self.arrangement
        arrangement.update(cues)
        if arrangement.section == "build" and arrangement.blackout(cues):
            return
        if arrangement.section == "drop":
            self.draw_drop(frame, cues)
        elif arrangement.section == "build":
            self.draw_build(frame, cues, arrangement.build_progress(cues))
        else:
            self.draw_breakdown(frame, cues, arrangement.age)
        if arrangement.reveal > 0.0:
            wash(frame, self.reveal_color, arrangement.reveal)

    @abstractmethod
    def draw_breakdown(self, frame, cues, seconds):
        """No kick: atmosphere. ``seconds`` is how long the breakdown has run."""

    @abstractmethod
    def draw_build(self, frame, cues, progress):
        """Rising tension, ``progress`` 0-1 toward the drop."""

    @abstractmethod
    def draw_drop(self, frame, cues):
        """Full energy, locked to the kick."""


# -- drawing primitives ------------------------------------------------------
def beam(frame, center, radius, color, strength):
    """A soft-edged line of light around ``center``, anti-aliased at both ends."""
    if strength <= 0.0:
        return
    reach = int(math.ceil(radius)) + 1
    for pixel in range(int(center) - reach, int(center) + reach + 2):
        amount = max(0.0, min(1.0, radius + 0.5 - abs(pixel - center)))
        if amount > 0.0:
            add(frame, pixel, scaled(color, amount * strength))


def mirrored(frame, distance, radius, color, strength):
    """Two beams at ``distance`` either side of the centre: stage symmetry."""
    middle = (frame.count - 1) / 2.0
    beam(frame, middle - distance, radius, color, strength)
    beam(frame, middle + distance, radius, color, strength)


def wash(frame, color, amount):
    """Blend the whole strip toward ``color``: a blinder or strobe hit."""
    amount = max(0.0, min(1.0, amount))
    frame.pixels = [blend(pixel, color, amount) for pixel in frame.pixels]


def fill(frame, color, strength, first=0, last=None):
    last = frame.count if last is None else last
    for index in range(max(0, first), min(frame.count, last)):
        add(frame, index, scaled(color, strength))


def ends(frame, size, color, strength):
    """The snare's place in every look: both ends of the strip."""
    fill(frame, color, strength, 0, size)
    fill(frame, color, strength, frame.count - size)


def glide(position):
    """Cosine ease for slow sweeps: lingers at the ends like a moving head."""
    return 0.5 - 0.5 * math.cos(2.0 * math.pi * position)
