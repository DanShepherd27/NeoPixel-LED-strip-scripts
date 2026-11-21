"""Mini-games for the LED arcade."""

from arcade.games.base import BaseGame
from arcade.games.reaction import ReactionGame
from arcade.games.dodge import DodgeGame
from arcade.games.shooter import ShooterGame
from arcade.games.pong import PongGame

# Registry: slug -> game class, in the order shown in the UI.
GAMES = {
    "reaction": ReactionGame,
    "dodge": DodgeGame,
    "shooter": ShooterGame,
    "pong": PongGame,
}


def game_catalog():
    """Return metadata about every available game for the web UI."""
    return [
        {
            "slug": cls.slug,
            "name": cls.name,
            "description": cls.description,
            "min_players": cls.min_players,
            "max_players": cls.max_players,
            "layouts": list(cls.layouts),
        }
        for cls in GAMES.values()
    ]


__all__ = ["BaseGame", "GAMES", "game_catalog"]
