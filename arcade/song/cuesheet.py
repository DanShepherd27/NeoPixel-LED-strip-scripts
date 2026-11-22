"""Loads and compiles a ``.ledcue.json`` show file (see docs/show-format.md).

Compiling happens once when a song starts: musical times become seconds,
presets and palettes are resolved, repeat rules are expanded, and every cue
is sorted by time. The result is plain tuples and lists, so playing the show
costs almost nothing per frame.
"""

import bisect
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

FORMAT = "ledcue"
VERSION = 1
OPS = ("go", "fire", "set", "stop", "seed")
DURATION_PATTERN = re.compile(r"^\s*([0-9.]+)\s*(b|bar|s)\s*$")


class ShowFileError(ValueError):
    """The file cannot be used at all (wrong format, bad tempo map...)."""


class TempoMap:
    """Piecewise-constant tempo: converts between seconds and beats."""

    def __init__(self, entries, ppq):
        if not entries:
            raise ShowFileError("time.tempo_map needs at least one entry")
        self.ppq = ppq
        self.beats_per_bar = int(entries[0].get("beats_per_bar", 4))
        self._starts, self._beats, self._spb = [], [], []
        beat = 0.0
        for index, entry in enumerate(entries):
            start, bpm = float(entry["at"]), float(entry["bpm"])
            if index:
                beat += (start - self._starts[-1]) / self._spb[-1]
            self._starts.append(start)
            self._beats.append(beat)
            self._spb.append(60.0 / bpm)

    def beat_at(self, seconds):
        """Beats since bar 1 beat 1 (negative before the first tempo entry)."""
        i = max(0, bisect.bisect_right(self._starts, seconds) - 1)
        return self._beats[i] + (seconds - self._starts[i]) / self._spb[i]

    def seconds_at(self, beat):
        i = max(0, bisect.bisect_right(self._beats, beat) - 1)
        return self._starts[i] + (beat - self._beats[i]) * self._spb[i]

    def parse_time(self, value):
        """Seconds for a number (seconds) or a ``"bar|beat|tick"`` string."""
        if isinstance(value, (int, float)):
            return float(value)
        try:
            bar, beat, tick = (int(part) for part in str(value).split("|"))
        except ValueError:
            raise ShowFileError("bad time %r (use seconds or 'bar|beat|tick')" % (value,))
        return self.seconds_at((bar - 1) * self.beats_per_bar + (beat - 1) + tick / self.ppq)

    def parse_duration(self, value, at):
        """Seconds for a duration number or ``"4b"``/``"2bar"``/``"0.5s"`` starting at ``at``."""
        if isinstance(value, (int, float)):
            return float(value)
        match = DURATION_PATTERN.match(str(value))
        if not match:
            raise ShowFileError("bad duration %r" % (value,))
        amount, unit = float(match.group(1)), match.group(2)
        if unit == "s":
            return amount
        beats = amount * (self.beats_per_bar if unit == "bar" else 1)
        start = self.beat_at(at)
        return self.seconds_at(start + beats) - self.seconds_at(start)


@dataclass
class Cue:
    time: float          # when the cue's effect should be heard/seen (song seconds)
    op: str
    track: str = ""
    pattern: str = ""
    params: dict = field(default_factory=dict)
    lead: float = 0.0    # start this many seconds early (anticipation)
    fade: float = 0.0    # fade_in for go, fade_out for stop
    cut: bool = False
    dur: float = 0.0     # fire: lifetime; set: ramp time
    vel: object = 1.0
    end: float = 0.0     # go: time of the next go/stop on the track (compile result)

    @property
    def start(self):
        return self.time - self.lead


@dataclass
class CueSheet:
    song: dict
    tempo: TempoMap
    tracks: list
    markers: list        # [(seconds, name)] sorted
    cues: list           # sorted by start time
    warnings: list
    path: Path = None

    @property
    def duration(self):
        return float(self.song["duration"])

    @property
    def marker_times(self):
        return [time for time, _ in self.markers]

    def marker_at(self, seconds):
        """``(index, name)`` of the section containing ``seconds``."""
        index = max(0, bisect.bisect_right(self.marker_times, seconds) - 1)
        return index, self.markers[index][1] if self.markers else ""


def _palette(value, palettes):
    colors = palettes.get(value, value) if isinstance(value, str) else value
    if not isinstance(colors, list):
        raise ShowFileError("unknown palette %r" % (value,))
    return [_color(c) for c in colors]


def _color(value):
    if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(int(c) for c in value)
    raise ShowFileError("bad color %r (use #RRGGBB)" % (value,))


def _resolve_params(raw, presets, palettes):
    """Merge a cue's preset and params; turn palette/color names into RGB tuples."""
    pattern = raw.get("pattern", "")
    params = {}
    if "preset" in raw:
        preset = presets.get(raw["preset"])
        if preset is None:
            raise ShowFileError("unknown preset %r" % raw["preset"])
        params.update(preset)
        pattern = pattern or preset.get("pattern", "")
    params.update(raw.get("params", {}))
    params.update({k: v for k, v in raw.items()
                   if k not in ("at", "op", "track", "preset", "params", "pattern", "every",
                                "until", "count", "lead", "fade_in", "fade_out", "cut", "dur",
                                "vel", "over", "ease")})
    params.pop("pattern", None)
    for key in ("palette", "colors"):
        if key in params:
            params[key] = _palette(params[key], palettes)
    for key in ("accent", "color", "core", "flash", "spark", "snare"):
        if key in params:
            params[key] = _color(params[key])
    return pattern, params


def _expand(raw, tempo):
    """Times for a cue, expanding ``every`` repeat rules."""
    start = tempo.parse_time(raw["at"])
    if "every" not in raw:
        return [start]
    limit = tempo.parse_time(raw["until"]) if "until" in raw else None
    count = int(raw["count"]) if "count" in raw else None
    if limit is None and count is None:
        raise ShowFileError("'every' needs 'until' or 'count'")
    times, beat = [], tempo.beat_at(start)
    step_seconds = tempo.parse_duration(raw["every"], start)
    step_beats = tempo.beat_at(start + step_seconds) - beat
    while (limit is None or tempo.seconds_at(beat) < limit - 1e-6) and \
            (count is None or len(times) < count):
        times.append(tempo.seconds_at(beat))
        beat += step_beats
    return times


def compile_cuesheet(data, path=None):
    """Compile parsed JSON into a :class:`CueSheet`. Bad cues become warnings."""
    if data.get("format") != FORMAT:
        raise ShowFileError("not a ledcue file")
    if int(data.get("version", 0)) > VERSION:
        raise ShowFileError("file version %s is newer than this player (%s)" % (data["version"], VERSION))
    song = data["song"]
    if "duration" not in song:
        raise ShowFileError("song.duration is required")
    time = data.get("time", {})
    tempo = TempoMap(time.get("tempo_map", []), int(time.get("ppq", 480)))
    palettes, presets = data.get("palettes", {}), data.get("presets", {})
    tracks = [dict(track) for track in data.get("tracks", [{"id": "base", "blend": "replace"}])]
    track_ids = {track["id"] for track in tracks}
    warnings, cues = [], []

    for raw in data.get("cues", []):
        try:
            op = raw["op"]
            if op not in OPS:
                raise ShowFileError("unknown op %r" % op)
            track = raw.get("track", "")
            if op != "seed" and track not in track_ids:
                raise ShowFileError("unknown track %r" % track)
            pattern, params = _resolve_params(raw, presets, palettes)
            for at in _expand(raw, tempo):
                cues.append(Cue(
                    time=at, op=op, track=track, pattern=pattern, params=params,
                    lead=tempo.parse_duration(raw.get("lead", 0), at),
                    fade=tempo.parse_duration(raw.get("fade_in" if op == "go" else "fade_out",
                                                     0.6 if op == "go" and not raw.get("cut") else 0), at),
                    cut=bool(raw.get("cut", False)),
                    dur=tempo.parse_duration(raw.get("dur", raw.get("over", 0)), at),
                    vel=raw.get("vel", 1.0),
                ))
        except (ShowFileError, KeyError, ValueError) as exc:
            warnings.append("cue %r skipped: %s" % (raw.get("at", "?"), exc))
    cues.sort(key=lambda cue: (cue.start, cue.time))

    ends = {}
    for cue in reversed(cues):  # a go lasts until the next go/stop on its track
        if cue.op in ("go", "stop"):
            if cue.op == "go":
                cue.end = ends.get(cue.track, float(song["duration"]) + 1.0)
            ends[cue.track] = cue.time

    markers = sorted((tempo.parse_time(m["at"]), m["name"]) for m in data.get("markers", []))
    return CueSheet(song, tempo, tracks, markers, cues, warnings, Path(path) if path else None)


def load_cuesheet(path):
    with open(path, "r", encoding="utf-8") as show_file:
        return compile_cuesheet(json.load(show_file), path)
