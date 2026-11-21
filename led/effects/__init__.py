"""Idle / attract-mode LED effects.

Each effect is a small object exposing ``render(frame, dt)``. They are
combined and rotated automatically by the arcade manager when nobody is
playing.
"""

from led.effects.rainbow import RainbowWave
from led.effects.comet import Comet
from led.effects.fire import Fire
from led.effects.twinkle import Twinkle
from led.effects.color_wave import ColorWave
from led.effects.christmas import Christmas
from led.effects.breathing import Breathing
from led.effects.particles import Particles

# Playlist of (display name, factory) used by the idle rotation.
EFFECTS = [
    ("Rainbow Wave", RainbowWave),
    ("Comet", Comet),
    ("Twinkle", Twinkle),
    ("Fire", Fire),
    ("Color Wave", ColorWave),
    ("Christmas", Christmas),
    ("Breathing", Breathing),
    ("Particles", Particles),
]

__all__ = [
    "RainbowWave",
    "Comet",
    "Fire",
    "Twinkle",
    "ColorWave",
    "Christmas",
    "Breathing",
    "Particles",
    "EFFECTS",
]
