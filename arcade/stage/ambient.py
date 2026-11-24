"""Idle-rotation effects: a stage look's breakdown on a steady 120 BPM clock.

Only the calm breakdown runs here, so attract mode keeps the look's atmosphere
(slow sweeps, haze, depth) without beats or flashes when no music is playing.
"""

from arcade.song.rhythm import BeatContext
from arcade.stage import create_look

IDLE_BPM = 120.0


class StageAmbient:
    """An idle effect (``render(frame, dt)``) for one stage look."""

    look_name = ""

    def __init__(self, count):
        self.count = count
        self.look = create_look(self.look_name, "breakdown")
        self.ctx = BeatContext()
        self.ctx.accent = 0.0
        self.ctx.level = 0.3
        self.ctx.bands = [0.2, 0.2, 0.25, 0.3, 0.25, 0.15]

    def render(self, frame, dt):
        ctx = self.ctx
        ctx.dt = dt
        ctx.t += dt
        ctx.beat = ctx.t * IDLE_BPM / 60.0
        ctx.beat_index = int(ctx.beat)
        ctx.beat_in_bar = ctx.beat_index % 4
        ctx.bar_in_section = ctx.beat_index // 4
        ctx.phase = 0.99   # no beat pops: the kick envelope stays near zero
        frame.clear()
        self.look.render(frame, ctx)


class GenesysAmbient(StageAmbient):
    look_name = "genesys"


class HoloAmbient(StageAmbient):
    look_name = "holo"


# (display name, factory) entries for the idle rotation.
AMBIENT_EFFECTS = [("Genesys Scan", GenesysAmbient), ("Holo Layers", HoloAmbient)]
