"""Song scene: turns the playback clock into LED frames."""

from arcade.song.analysis import SongAnalysis
from arcade.song.effects import GREEN, RED, GOLD, WARM
from arcade.song.moods import Afterglow, Bells, Verse, Whisper
from arcade.song.peaks import Build, Chorus, Dream, Finale
from arcade.song.rhythm import BeatContext
from arcade.song.timeline import BEAT, BEAT_OFFSET, SECTIONS, section_at
from led.frame import Frame

CROSSFADE_SECONDS = 0.6


def build_moods():
    return {
        "bells": Bells(),
        "verse": Verse(),
        "verse_green": Verse(colors=(GREEN, WARM)),
        "rising": Verse(colors=(RED, GOLD), lively=True),
        "whisper": Whisper(),
        "build": Build(),
        "chorus": Chorus(),
        "chorus_gold": Chorus(colors=(RED, GOLD, GREEN, WARM), accent=WARM),
        "dream": Dream(),
        "finale": Finale(),
        "afterglow": Afterglow(),
    }


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
        self._last_eighth = None
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
        self.moods[section.mood].render(frame, ctx)
        if self._fade < 1.0 and self._previous_mood:
            self._fade = min(1.0, self._fade + dt / CROSSFADE_SECONDS)
            scratch = self._scratch
            scratch.clear()
            self.moods[self._previous_mood].render(scratch, ctx)
            frame.pixels = [
                tuple(int(round(old[c] + (new[c] - old[c]) * self._fade)) for c in range(3))
                for old, new in zip(scratch.pixels, frame.pixels)
            ]

    def _update_context(self, t, dt):
        ctx = self.ctx
        features = self.analysis.at(t)
        beat = (t - BEAT_OFFSET) / BEAT
        beat_index = int(beat // 1)
        eighth = int((beat * 2) // 1)
        ctx.new_beat = self._last_beat is not None and beat_index != self._last_beat
        ctx.new_eighth = self._last_eighth is not None and eighth != self._last_eighth
        self._last_beat, self._last_eighth = beat_index, eighth
        ctx.new_bar = ctx.new_beat and beat_index % 4 == 0
        ctx.t, ctx.dt, ctx.beat, ctx.beat_index = t, dt, beat, beat_index
        ctx.phase = beat - beat_index
        ctx.beat_in_bar = beat_index % 4
        ctx.accent, ctx.offbeat_accent = self.analysis.beat_accent(beat_index)
        _, _, ctx.progress, ctx.bar_in_section = section_at(t)
        ctx.bands = features["bands"]
        ctx.level = features["level"]
        ctx.kick = features["kick"]
        ctx.snare = features["snare"]
        return ctx
