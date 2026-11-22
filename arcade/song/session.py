"""One run of the song show: playback clock, Pi audio, and choreography."""

import time

from arcade.song.analysis import SONG_AUDIO, SongAnalysis
from arcade.song.choreography import SongChoreography
from arcade.song.player import PiAudioPlayer
from arcade.song.timeline import section_at

END_PADDING_SECONDS = 1.0


class SongSession:
    def __init__(self, count, pi_audio, audio_latency_ms=250, analysis=None):
        self.pi_audio = pi_audio
        self.audio_latency = audio_latency_ms / 1000.0
        self.choreography = SongChoreography(count, analysis or SongAnalysis())
        self.duration = self.choreography.duration
        self.pi_audio_error = None
        self._player = PiAudioPlayer(SONG_AUDIO)
        self._started = None
        if pi_audio:
            self.pi_audio_error = self._player.start()
        self._started = time.monotonic()

    @property
    def position(self):
        """Seconds of the song being heard, allowing for audio start-up delay."""
        elapsed = time.monotonic() - self._started
        return max(0.0, elapsed - (self.audio_latency if self.pi_audio else 0.0))

    @property
    def finished(self):
        return self.position >= self.duration + END_PADDING_SECONDS

    def render(self, frame, dt):
        self.choreography.render(frame, self.position, dt)

    def stop(self):
        self._player.stop()

    def snapshot(self):
        index, section, _, _ = section_at(self.position)
        return {
            "position": round(min(self.position, self.duration), 2),
            "duration": round(self.duration, 2),
            "section": section.name,
            "section_index": index,
            "pi_audio": self.pi_audio,
            "pi_audio_error": self.pi_audio_error,
        }
