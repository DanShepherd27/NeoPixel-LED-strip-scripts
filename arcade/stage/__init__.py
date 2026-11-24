"""Stage looks: lighting styles distilled from artists' live shows.

Research notes and the design rules they share are in ``docs/stage-looks.md``.
Add a look by subclassing ``StageLook`` and registering it in ``LOOKS``; the live
visualizer, generated song shows and the idle rotation all pick it up from there.
"""

from arcade.stage.base import StageLook
from arcade.stage.genesys import GenesysLook
from arcade.stage.holo import HoloLook
from arcade.stage.paradise import ParadiseLook
from arcade.stage.rave import RaveLook

# name -> look class. The name is used as the live pattern name and in show files.
LOOKS = {
    "genesys": GenesysLook,
    "holo": HoloLook,
    "paradise": ParadiseLook,
    "rave": RaveLook,
}


def create_look(name, section=None):
    """A new look; ``section`` pins breakdown/build/drop (song shows), None infers it."""
    return LOOKS[name](section)


__all__ = ["LOOKS", "StageLook", "create_look"]
