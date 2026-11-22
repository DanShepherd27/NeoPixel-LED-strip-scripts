"""Pattern library: what the names in a show file's cues mean.

Each pattern is an object with ``render(frame, ctx)``; looping patterns are
started with ``go`` cues and one-shots with ``fire`` cues. The file supplies
only parameters (palette, speed, ...); no code ever comes from a show file.
"""

from arcade.song.effects import GOLD, GREEN, RED, WARM, WHITE_HOT, Comets
from arcade.song.moods import Afterglow, Bells, Verse, Whisper
from arcade.song.peaks import Build, Chorus, Dream, Finale


class CometShot:
    """One-shot: a bright head crossing the strip, hopping a few pixels at a time."""

    def __init__(self, params):
        self.params = params
        self.comets = Comets(int(params.get("quantum", 3)))
        self._launched = False
        self.finished = False

    def render(self, frame, ctx):
        if not self._launched:
            up = self.params.get("dir", "up") == "up"
            self.comets.launch(
                1 if up else -1, float(self.params.get("speed", 26.0)),
                self.params.get("color", GOLD), int(self.params.get("tail", 7)), frame.count,
            )
            self._launched = True
        self.comets.draw(frame, ctx.dt, 0.8 + 0.2 * ctx.level)
        self.finished = not self.comets.items


def _verse(params):
    colors = tuple(params.get("palette", [RED, WARM]))[:2]
    return Verse(colors=colors, lively=bool(params.get("lively", False)),
                 accent=params.get("accent", GOLD), flash=params.get("flash", WARM))


def _chorus(params):
    return Chorus(colors=tuple(params.get("palette", [RED, GREEN, WARM])),
                  accent=params.get("accent", GOLD), spark=params.get("spark", WARM),
                  snare=params.get("snare", WHITE_HOT))


# name -> factory(params); ONE_SHOTS only make sense with ``fire`` cues.
PATTERNS = {
    "bells": lambda params: Bells(),
    "verse_dots": _verse,
    "whisper": lambda params: Whisper(),
    "riser": lambda params: Build(params.get("style", "ice")),
    "chorus_dots": _chorus,
    "ribbons": lambda params: Dream(params.get("color")),
    "finale": lambda params: Finale(),
    "afterglow": lambda params: Afterglow(tuple(params.get("palette", [WARM, GOLD, RED, GREEN]))),
    "comet": CometShot,
}
ONE_SHOTS = {"comet"}


def create_pattern(name, params):
    """A new pattern instance, or KeyError for a name this player does not know."""
    return PATTERNS[name](params)
