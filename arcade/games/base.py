"""Common game interface.

Every game subclasses :class:`BaseGame` and implements the lifecycle hooks.
Games produce pixels via ``render(frame, dt)`` and expose state for the web
UI via ``get_state()``. They never touch hardware directly.
"""

import logging

log = logging.getLogger("arcade.games")


class BaseGame:
    #: Human-readable name shown in the UI.
    name = "Game"
    #: Stable identifier used in API routes.
    slug = "game"
    #: Short description for the game-select screen.
    description = ""
    #: Minimum players required (None means no minimum beyond 1).
    min_players = 1
    #: Maximum players (None means unlimited).
    max_players = None
    #: Physical strip orientations this game is designed to support.
    layouts = ("horizontal", "vertical")

    def __init__(self, manager):
        self.manager = manager
        self.players = []
        self.running = False
        self.finished = False
        self.elapsed = 0.0
        self.winner = None
        self.results = {}

    # -- lifecycle ----------------------------------------------------------
    def setup(self, players):
        """Receive the players participating in this game."""
        self.players = list(players)
        for p in self.players:
            p.score = 0
            p.extra = {}

    def start(self):
        """Called when the game begins (after countdown)."""
        self.running = True
        self.finished = False
        self.elapsed = 0.0
        self.winner = None
        self.results = {}

    def end(self):
        """Called when the game finishes; populate ``self.results``."""
        self.running = False
        self.finished = True

    def reset(self):
        self.running = False
        self.finished = False
        self.elapsed = 0.0
        self.winner = None
        self.results = {}

    # -- per-frame hooks ----------------------------------------------------
    def update(self, dt):
        """Advance game logic by ``dt`` seconds."""
        if self.running:
            self.elapsed += dt

    def handle_input(self, player_id, action):
        """Handle a player input action (e.g. 'fire', 'left', 'right')."""

    def render(self, frame, dt):
        """Fill ``frame`` with the current game view."""

    def get_state(self):
        """Return a JSON-serialisable snapshot for the web UI."""
        return {
            "name": self.name,
            "slug": self.slug,
            "running": self.running,
            "finished": self.finished,
            "elapsed": self.elapsed,
            "winner": self.winner,
            "results": self.results,
        }
