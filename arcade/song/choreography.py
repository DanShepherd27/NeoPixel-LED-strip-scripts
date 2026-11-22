"""Song scene: turns the playback clock into LED frames."""

from arcade.song.analysis import SongAnalysis
from arcade.song.moods import BeatContext, build_moods
from arcade.song.timeline import BEAT, BEAT_OFFSET, SECTIONS, section_at
from led.frame import Frame

CROSSFADE_SECONDS = 0.9


class SongChoreography:
    def __init__(self, count, analysis=None):
        self.count = count
        self.analysis = analysis or SongAnalysis()
        self.duration = self.analysis.duration
        self.moods = build_moods()
        self.ctx = BeatContext()
        self._section_index = -1
        self._previous_mood = None
        self._fade = 1.0
        self._last_beat = None
        self._scratch = Frame(count)

    @property
    def section_name(self):
        return SECTIONS[max(0, self._section_index)].name

    def render(self, frame, t, dt):
        """Draw the show at song time ``t`` seconds into ``frame``."""
        ctx = self._update_context(t, dt)
        index, section, _, _ = section_at(t)
        if index != self._section_index:
            if section.cut or self._section_index < 0:
                self._previous_mood = None
            else:
                self._previous_mood = SECTIONS[self._section_index].mood
            self._section_index = index
            self._fade = 0.0 if self._previous_mood else 1.0
        mood = self.moods[section.mood]
        mood.render(frame, ctx)
        if self._fade < 1.0 and self._previous_mood:
            self._fade = min(1.0, self._fade + dt / CROSSFADE_SECONDS)
            scratch = self._scratch
            scratch.clear()
            self.moods[self._previous_mood].render(scratch, ctx)
            amount = self._fade
            frame.pixels = [
                tuple(int(round(old[c] + (new[c] - old[c]) * amount)) for c in range(3))
                for old, new in zip(scratch.pixels, frame.pixels)
            ]

    def _update_context(self, t, dt):
        ctx = self.ctx
        features = self.analysis.at(t)
        beat = (t - BEAT_OFFSET) / BEAT
        beat_index = int(beat // 1)
        ctx.new_beat = self._last_beat is not None and beat_index != self._last_beat
        self._last_beat = beat_index
        ctx.new_bar = ctx.new_beat and beat_index % 4 == 0
        ctx.t, ctx.dt, ctx.beat = t, dt, beat
        ctx.phase = beat - beat_index
        ctx.beat_in_bar = beat_index % 4
        _, _, ctx.progress, ctx.bar_in_section = section_at(t)
        ctx.bands = features["bands"]
        ctx.level = features["level"]
        ctx.kick = features["kick"]
        ctx.snare = features["snare"]
        return ctx
