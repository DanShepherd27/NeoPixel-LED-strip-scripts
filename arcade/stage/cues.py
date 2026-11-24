"""What a stage look reads from the music, and which part of the track is playing.

``StageCues`` gives one frame's beat information in the same shape for a song show
(an exact tempo map) and for live input (a tracked grid, or detected hits until it
locks). ``Arrangement`` decides whether the music is in a **breakdown**, a **build**
or a **drop**: a song show names the section in its cue; live input infers it from
whether the kick is playing and how loud the music is against its recent average.
"""

import math

from arcade.music_dynamics import follow, live_pop, pop

PHRASE_BARS = 8                 # looks change color/geometry only at phrase starts
SECTIONS = ("breakdown", "build", "drop")
REVEAL_SECONDS = 0.35           # the one big flash when a drop lands


class StageCues:
    """One frame of musical cues, read from a song or live ``BeatContext``."""

    def __init__(self, ctx, dynamics=None, intensity=1.0, period=0.5):
        live = hasattr(ctx, "locked")
        self.ctx = ctx
        self.dt = max(0.0, ctx.dt)
        self.t = ctx.t
        self.grid = ctx.locked if live else True
        self.bar_known = (ctx.locked and ctx.bar_known) if live else True
        self.period = ctx.period if live else period
        # Hits fade over a fixed ~150 ms (like a stage flash), not a share of the beat.
        on_grid = pop(ctx.phase * self.period, ctx.accent)
        self.kick = live_pop(ctx) if live else on_grid
        if live and not (ctx.locked and ctx.backbeat_known):
            self.snare = ctx.snare_hit
        else:
            self.snare = on_grid if ctx.is_backbeat else 0.0
        self.new_beat = ctx.beat_event if live else ctx.new_beat
        self.kick_heard = ctx.new_kick if live else ctx.new_beat
        self.downbeat = self.kick if self.bar_known and ctx.is_downbeat else 0.0
        self.beat_in_bar = ctx.beat_in_bar if self.bar_known else 0
        # Beats since the start, used for slow tempo-locked motion.
        self.beats = ctx.beat if self.grid else ctx.t / self.period
        self.bar_in_section = ctx.bar_in_section if self.bar_known else 0
        self.phrase = self.bar_in_section // PHRASE_BARS
        self.level = max(0.0, min(1.0, ctx.level))
        self.bands = [max(0.0, min(1.0, value)) for value in ctx.bands]
        self.progress = ctx.progress
        # How hard effects react: 0 = barely, 1 = default, 2 = maximum (the FX knob).
        self.fx = max(0.0, min(2.0, intensity))
        self.energy = dynamics.energy if dynamics else 0.7
        self.surge = dynamics.surge if dynamics else 0.0
        # The pop used for hits: the beat; until a live beat grid locks, also any
        # sudden jump in loudness, so the lights react from the first second.
        self.hit = self.kick if self.grid else min(1.0, max(self.kick, self.surge))
        # Overall brightness follows the music's volume; the knob widens the range.
        depth = min(0.85, 0.55 * self.fx)
        self.volume = 1.0 - depth + depth * self.energy

    def drive(self, rest, peak, signal):
        """Brightness from ``rest`` toward ``peak`` as ``signal`` rises. The FX knob
        lowers the rest and steepens the rise, so hits stand out more."""
        rest *= max(0.4, min(1.4, 1.4 - 0.5 * self.fx))
        return max(0.0, min(1.0, rest + (peak - rest) * min(1.0, signal * (0.4 + 0.6 * self.fx))))

    def bars(self, count):
        """0-1 position through a cycle of ``count`` bars, locked to the beat grid."""
        return (self.beats / (4.0 * count)) % 1.0

    @property
    def vocal(self):
        """Mid/high-mid energy: voices, pads and leads rather than drums."""
        return 0.6 * self.bands[3] + 0.4 * self.bands[4]


class Arrangement:
    """Tracks the section. ``fixed`` (from a song show's cue) pins it; otherwise live
    audio decides: no kick for a while is a breakdown, a breakdown swelling above its
    recent loudness is a build, and the kick coming back is the drop."""

    MIN_BREAK_FOR_REVEAL = 4.0   # seconds without the kick before a drop gets the reveal
    HOLD = 1.0                   # seconds a breakdown/build change must persist

    def __init__(self, fixed=None):
        self.fixed = fixed if fixed in SECTIONS else None
        self.section = self.fixed or "breakdown"
        self.age = 0.0               # seconds in the current section
        self.fast, self.slow = 0.0, None
        self.since_kick = math.inf
        self.silence = math.inf       # how long the kick was gone before it last returned
        self.pending, self.pending_age = None, 0.0
        self.reveal_left = 0.0
        self._first = True

    @property
    def reveal(self):
        """1.0 the moment a drop lands, fading to 0 over ``REVEAL_SECONDS``."""
        return max(0.0, self.reveal_left / REVEAL_SECONDS)

    def update(self, cues):
        dt = cues.dt
        self.age += dt
        self.reveal_left = max(0.0, self.reveal_left - dt)
        if self.fixed:
            if self._first and self.fixed == "drop":
                self.reveal_left = REVEAL_SECONDS
            self._first = False
            return
        self.fast = follow(self.fast, cues.level, dt, 6.0, 2.5)
        if self.slow is None:
            self.slow = cues.level
        self.slow += (cues.level - self.slow) * (1.0 - math.exp(-dt / 10.0))
        self.since_kick += dt
        if cues.kick_heard:
            self.silence, self.since_kick = self.since_kick, 0.0
        target = self._target(cues)
        if target == "drop" and self.section != "drop":
            self._enter("drop", reveal=self.silence >= self.MIN_BREAK_FOR_REVEAL)
        elif target != self.section:
            self.pending_age = self.pending_age + dt if self.pending == target else 0.0
            self.pending = target
            if self.pending_age >= self.HOLD:
                self._enter(target)
        else:
            self.pending = None

    def build_progress(self, cues):
        if self.fixed:
            return cues.progress
        return min(1.0, self.age / (16.0 * cues.period))   # a typical 4-bar riser

    def blackout(self, cues):
        """The breath before the drop: the last half beat of a song show's build."""
        ctx = cues.ctx
        return (self.fixed == "build" and cues.progress > 0.8
                and ctx.beat_in_bar == 3 and ctx.phase >= 0.5)

    def _target(self, cues):
        drive = self.since_kick < max(1.2, 2.5 * cues.period)
        if drive and self.fast > 0.6 * self.slow:
            return "drop"
        if self.section == "drop" and drive:
            return "drop"
        swelling = self.fast > (0.85 if self.section == "build" else 1.05) * self.slow
        return "build" if swelling else "breakdown"

    def _enter(self, section, reveal=False):
        self.section, self.age = section, 0.0
        self.pending, self.pending_age = None, 0.0
        if reveal:
            self.reveal_left = REVEAL_SECONDS
