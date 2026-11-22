"""Cue engine: plays a compiled :class:`CueSheet` onto LED frames.

Each frame it launches the cues that have become due, renders every track's
patterns into a scratch frame and composites the tracks bottom to top. State
is tracking-style (like a lighting console): ``seek`` rebuilds what each track
would be showing at the target time by replaying ``go``/``set``/``stop`` cues,
so jumping around a song gives the same picture as playing through it.
"""

import math
import random

from arcade.song.patterns import ONE_SHOTS, create_pattern
from arcade.song.rhythm import BeatContext
from led.frame import Frame

REBUILD_FIRE_WINDOW = 0.25   # on seek, restart one-shots launched this recently
MAX_ONE_SHOT_SECONDS = 30.0


class _Instance:
    def __init__(self, pattern, cue):
        self.pattern = pattern
        self.cue = cue


class _Track:
    def __init__(self, spec, count):
        self.id = spec["id"]
        self.blend = spec.get("blend", "add")
        self.scratch = Frame(count)
        self.layer = Frame(count)
        self.reset()

    def reset(self):
        self.current = None
        self.previous = None
        self.fade_start = self.fade_len = 0.0
        self.stop_start = self.stop_len = None
        self.shots = []
        self.gain = 1.0
        self.ramp = None   # (from, to, start, length)


def _mix(old, new, amount):
    return [tuple(int(round(a[c] + (b[c] - a[c]) * amount)) for c in range(3))
            for a, b in zip(old, new)]


def _composite(dest, src, blend):
    if blend == "replace":
        dest.pixels = list(src.pixels)
    elif blend == "over":
        dest.pixels = [s if any(s) else d for d, s in zip(dest.pixels, src.pixels)]
    else:
        dest.pixels = [tuple(min(255, d[c] + s[c]) for c in range(3))
                       for d, s in zip(dest.pixels, src.pixels)]


class CueEngine:
    def __init__(self, sheet, analysis, count):
        self.sheet = sheet
        self.analysis = analysis
        self.count = count
        self.duration = sheet.duration
        self.tracks = [_Track(spec, count) for spec in sheet.tracks]
        self._tracks = {track.id: track for track in self.tracks}
        self.ctx = BeatContext()
        self._next = 0
        self._last_beat = self._last_eighth = None
        self._beat_aligned = len(sheet.tempo._starts) == 1

    @property
    def section_name(self):
        return self.sheet.marker_at(self.ctx.t)[1]

    # -- playing -------------------------------------------------------------
    def seek(self, seconds):
        """Rebuild every track as it would be at ``seconds`` and continue from there."""
        for track in self.tracks:
            track.reset()
        self._last_beat = self._last_eighth = None
        cues = self.sheet.cues
        index = 0
        while index < len(cues) and cues[index].start <= seconds:
            self._apply(cues[index], seconds, rebuilding=True)
            index += 1
        self._next = index
        self.ctx.t = seconds

    def render(self, frame, t, dt):
        """Draw the show at song time ``t`` seconds into ``frame``."""
        cues = self.sheet.cues
        while self._next < len(cues) and cues[self._next].start <= t:
            self._apply(cues[self._next], t, rebuilding=False)
            self._next += 1
        ctx = self._update_context(t, dt)
        for track in self.tracks:
            self._render_track(track, ctx)
            _composite(frame, track.layer, track.blend)

    # -- cue handling --------------------------------------------------------
    def _apply(self, cue, now, rebuilding):
        if cue.op == "seed":
            random.seed(cue.params.get("value", 0))
            return
        track = self._tracks[cue.track]
        if cue.op == "go":
            self._go(track, cue, now, rebuilding)
        elif cue.op == "stop":
            if rebuilding and now - cue.time >= cue.fade:
                track.current = track.previous = None
            else:
                track.stop_start, track.stop_len = cue.time, max(cue.fade, 1e-3)
        elif cue.op == "set":
            self._set(track, cue, now, rebuilding)
        elif cue.op == "fire":
            if rebuilding and now - cue.time > REBUILD_FIRE_WINDOW:
                return
            self._fire(track, cue)

    def _make(self, cue):
        try:
            return _Instance(create_pattern(cue.pattern, cue.params), cue)
        except KeyError:
            if cue.pattern not in self.sheet.warnings:
                self.sheet.warnings.append("unknown pattern %r ignored" % cue.pattern)
            return None

    def _go(self, track, cue, now, rebuilding):
        instance = self._make(cue)
        if instance is None:
            return
        track.stop_start = track.stop_len = None
        if rebuilding or cue.cut or track.current is None:
            track.current, track.previous = instance, None
            track.fade_start, track.fade_len = cue.time, 0.0
        else:
            track.previous, track.current = track.current, instance
            track.fade_start, track.fade_len = cue.time, max(cue.fade, 1e-3)

    def _set(self, track, cue, now, rebuilding):
        params = dict(cue.params)
        if "brightness" in params:
            target = float(params.pop("brightness"))
            if rebuilding and now >= cue.time + cue.dur:
                track.gain, track.ramp = target, None
            else:
                track.ramp = (track.gain, target, cue.time, max(cue.dur, 1e-3))
        if params and track.current and hasattr(track.current.pattern, "update"):
            track.current.pattern.update(params)

    def _fire(self, track, cue):
        instance = self._make(cue)
        if instance is not None:
            track.shots.append(instance)

    # -- rendering -----------------------------------------------------------
    def _update_context(self, t, dt):
        ctx, tempo = self.ctx, self.sheet.tempo
        beat = tempo.beat_at(t)
        beat_index = int(math.floor(beat))
        eighth = int(math.floor(beat * 2))
        ctx.new_beat = self._last_beat is not None and beat_index != self._last_beat
        ctx.new_eighth = self._last_eighth is not None and eighth != self._last_eighth
        self._last_beat, self._last_eighth = beat_index, eighth
        ctx.new_bar = ctx.new_beat and beat_index % tempo.beats_per_bar == 0
        ctx.t, ctx.dt, ctx.beat, ctx.beat_index = t, dt, beat, beat_index
        ctx.phase = beat - beat_index
        ctx.beat_in_bar = beat_index % tempo.beats_per_bar
        if self._beat_aligned:
            ctx.accent, ctx.offbeat_accent = self.analysis.beat_accent(beat_index)
        else:
            ctx.accent, ctx.offbeat_accent = 0.5, 0.3
        features = self.analysis.at(t)
        ctx.bands, ctx.level = features["bands"], features["level"]
        ctx.kick, ctx.snare = features["kick"], features["snare"]
        return ctx

    def _draw(self, instance, scratch, ctx, one_shot=False):
        """Render one pattern instance into ``scratch`` with its own timing context."""
        cue, tempo = instance.cue, self.sheet.tempo
        age = ctx.t - cue.time
        length = max(cue.dur, 1.0) if one_shot else max(cue.end - cue.time, 1e-3)
        ctx.progress = max(0.0, min(1.0, age / length))
        per_bar = tempo.beats_per_bar
        ctx.bar_in_section = max(0, int(math.floor(ctx.beat / per_bar)
                                        - math.floor(tempo.beat_at(cue.time) / per_bar)))
        instance.pattern.render(scratch, ctx)

    def _render_track(self, track, ctx):
        layer, scratch = track.layer, track.scratch
        layer.clear()
        if track.current is not None:
            scratch.clear()
            self._draw(track.current, scratch, ctx)
            layer.pixels = list(scratch.pixels)
            fading = track.previous is not None
            if fading:
                amount = (ctx.t - track.fade_start) / track.fade_len if track.fade_len else 1.0
                if amount >= 1.0:
                    track.previous = None
                else:
                    scratch.clear()
                    self._draw(track.previous, scratch, ctx)
                    layer.pixels = _mix(scratch.pixels, layer.pixels, max(0.0, amount))
        for shot in list(track.shots):
            scratch.clear()
            self._draw(shot, scratch, ctx, one_shot=True)
            _composite(layer, scratch, "add")
            cue = shot.cue
            expired = ctx.t - cue.time > (cue.dur if cue.dur > 0 else MAX_ONE_SHOT_SECONDS)
            if getattr(shot.pattern, "finished", False) or expired or \
                    ctx.t - cue.time > MAX_ONE_SHOT_SECONDS:
                track.shots.remove(shot)
        gain = self._gain(track, ctx.t)
        if track.stop_start is not None:
            gain *= max(0.0, 1.0 - (ctx.t - track.stop_start) / track.stop_len)
            if ctx.t - track.stop_start >= track.stop_len:
                track.current = track.previous = None
                track.stop_start = track.stop_len = None
        if gain < 0.999:
            layer.dim(gain)

    def _gain(self, track, t):
        if track.ramp is None:
            return track.gain
        start_value, end_value, start, length = track.ramp
        amount = (t - start) / length
        if amount >= 1.0:
            track.gain, track.ramp = end_value, None
            return end_value
        return start_value + (end_value - start_value) * max(0.0, amount)
