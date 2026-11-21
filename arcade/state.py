"""Arcade lifecycle states."""

from enum import Enum


class ArcadeState(Enum):
    IDLE = "idle"
    MUSIC = "music"
    LOBBY = "lobby"
    TUTORIAL = "tutorial"
    COUNTDOWN = "countdown"
    GAME = "game"
    RESULTS = "results"
    TRANSITION = "transition"
