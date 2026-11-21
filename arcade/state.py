"""Arcade lifecycle states."""

from enum import Enum


class ArcadeState(Enum):
    IDLE = "idle"
    LOBBY = "lobby"
    COUNTDOWN = "countdown"
    GAME = "game"
    RESULTS = "results"
    TRANSITION = "transition"
