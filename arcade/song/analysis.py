"""Pre-computed audio features for the song (see tools/analyze_song.py)."""

import base64
import json
from pathlib import Path

SONG_DIR = Path(__file__).resolve().parents[2] / "assets" / "song"
SONG_AUDIO = SONG_DIR / "all-i-want-for-christmas-is-you.mp3"
SONG_ANALYSIS = SONG_DIR / "all-i-want-for-christmas-is-you.analysis.json"
BAND_CHANNELS = ("sub", "bass", "low_mid", "mid", "high_mid", "high")


class SongAnalysis:
    def __init__(self, path=SONG_ANALYSIS):
        data = json.loads(Path(path).read_text())
        self.frame_rate = data["frame_rate"]
        self.duration = data["duration"]
        self._channels = {
            name: base64.b64decode(encoded) for name, encoded in data["channels"].items()
        }
        self.frames = data["frames"]
        self.tempo = data["tempo"]
        self._beat_strength = base64.b64decode(data["beat_strength"])
        self._offbeat_strength = base64.b64decode(data["offbeat_strength"])

    def _sample(self, name, position):
        values = self._channels[name]
        low = max(0, min(self.frames - 1, int(position)))
        high = min(self.frames - 1, low + 1)
        mix = position - int(position)
        return (values[low] * (1.0 - mix) + values[high] * mix) / 255.0

    def level_series(self, step, count, first=0.0):
        """Loudness sampled every ``step`` seconds starting at ``first``."""
        return [self._sample("level", max(0.0, first + i * step) * self.frame_rate)
                for i in range(count)]

    def at(self, seconds):
        """Interpolated features at ``seconds``: bands, level, kick, snare."""
        position = max(0.0, seconds) * self.frame_rate
        return {
            "bands": [self._sample(name, position) for name in BAND_CHANNELS],
            "level": self._sample("level", position),
            # Onsets last a single frame; take the strongest nearby sample.
            "kick": max(self._sample("kick", position + o) for o in (-1, 0)),
            "snare": max(self._sample("snare", position + o) for o in (-1, 0)),
        }

    def beat_accent(self, beat_index):
        """(on-beat, off-beat) onset strength 0-1 for the beat at ``beat_index``."""
        if not 0 <= beat_index < len(self._beat_strength):
            return 0.5, 0.3
        return (self._beat_strength[beat_index] / 255.0,
                self._offbeat_strength[beat_index] / 255.0)
