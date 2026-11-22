"""Stdlib tests for the cue format, engine and MIDI compiler: python -m unittest discover tests"""

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from arcade.song.cuesheet import compile_cuesheet, load_cuesheet  # noqa: E402
from arcade.song.engine import CueEngine  # noqa: E402
from arcade.song.library import load_song  # noqa: E402
from arcade.song.patterns import PATTERNS  # noqa: E402
from compile_show import compile_midi  # noqa: E402
from led.frame import Frame  # noqa: E402

BASE = {
    "format": "ledcue", "version": 1,
    "song": {"id": "t", "duration": 60.0},
    "time": {"ppq": 480, "tempo_map": [{"at": 1.0, "bpm": 120, "beats_per_bar": 4}]},
    "palettes": {"p": ["#FF0000", "#00FF00"]},
    "tracks": [{"id": "base", "blend": "replace"}, {"id": "fx", "blend": "add"}],
    "presets": {"dots": {"pattern": "verse_dots", "palette": "p"}},
}


def show(cues, **extra):
    return compile_cuesheet(dict(BASE, cues=cues, **extra))


class TimeTests(unittest.TestCase):
    def test_musical_time_uses_tempo_map(self):
        sheet = show([])
        self.assertAlmostEqual(sheet.tempo.parse_time("1|1|0"), 1.0)
        self.assertAlmostEqual(sheet.tempo.parse_time("2|1|0"), 3.0)      # 4 beats at 120 BPM
        self.assertAlmostEqual(sheet.tempo.parse_time("1|2|240"), 1.75)   # 1.5 beats
        self.assertAlmostEqual(sheet.tempo.parse_duration("2bar", 1.0), 4.0)

    def test_tempo_change_moves_later_cues(self):
        data = dict(BASE, cues=[{"at": "3|1|0", "op": "go", "track": "base", "pattern": "bells"}])
        data["time"] = {"ppq": 480, "tempo_map": [
            {"at": 1.0, "bpm": 120, "beats_per_bar": 4}, {"at": 3.0, "bpm": 60}]}
        # bar 3 starts 8 beats in: 4 beats at 120 BPM (2 s), then 4 beats at 60 BPM (4 s)
        self.assertAlmostEqual(compile_cuesheet(data).cues[0].time, 7.0)


class CompileTests(unittest.TestCase):
    def test_repeat_rule_and_preset_merge(self):
        sheet = show([
            {"at": "1|1|0", "op": "go", "track": "base", "preset": "dots", "lively": True},
            {"at": "1|1|0", "op": "fire", "track": "fx", "pattern": "comet", "dur": "1bar",
             "every": "1bar", "until": "4|1|0"},
        ])
        go, *shots = sheet.cues
        self.assertEqual(go.pattern, "verse_dots")
        self.assertEqual(go.params["palette"], [(255, 0, 0), (0, 255, 0)])
        self.assertTrue(go.params["lively"])
        self.assertEqual([round(c.time, 3) for c in shots], [1.0, 3.0, 5.0])

    def test_bad_cues_become_warnings_not_errors(self):
        sheet = show([{"at": "1|1|0", "op": "explode", "track": "base"},
                      {"at": "1|1|0", "op": "go", "track": "nope", "pattern": "bells"},
                      {"at": "1|1|0", "op": "go", "track": "base", "pattern": "bells"}])
        self.assertEqual(len(sheet.cues), 1)
        self.assertEqual(len(sheet.warnings), 2)

    def test_go_lasts_until_next_go_on_same_track(self):
        sheet = show([{"at": 5, "op": "go", "track": "base", "pattern": "bells"},
                      {"at": 9, "op": "go", "track": "base", "pattern": "whisper"}])
        self.assertEqual([c.end for c in sheet.cues], [9, 61.0])

    def test_newer_version_is_rejected(self):
        with self.assertRaises(ValueError):
            compile_cuesheet(dict(BASE, version=99, cues=[]))


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.song = load_song()

    def make(self):
        return CueEngine(self.song.sheet, self.song.analysis, 60)

    def test_bundled_show_has_no_warnings_and_known_patterns(self):
        sheet = load_cuesheet(ROOT / "assets/song/all-i-want-for-christmas-is-you.ledcue.json")
        self.assertEqual(sheet.warnings, [])
        self.assertTrue({c.pattern for c in sheet.cues if c.pattern} <= set(PATTERNS))

    def test_plays_the_whole_song_with_valid_pixels(self):
        engine, frame, t = self.make(), Frame(60), 0.0
        while t < 242.0:
            frame.clear()
            engine.render(frame, t, 0.05)
            self.assertEqual(len(frame.pixels), 60)
            self.assertTrue(all(0 <= c <= 255 for p in frame.pixels for c in p))
            t += 0.05

    def test_seek_rebuilds_the_same_tracks_as_playing_through(self):
        played, frame = self.make(), Frame(60)
        t = 0.0
        while t < 100.0:
            frame.clear()
            played.render(frame, t, 0.025)
            t += 0.025
        jumped = self.make()
        jumped.seek(100.0)
        names = lambda engine: [type(tr.current.pattern).__name__ if tr.current else None
                                for tr in engine.tracks]
        self.assertEqual(names(played), names(jumped))

    def test_latency_is_only_a_clock_shift(self):
        # The same song time must give the same picture whatever the latency was:
        # the engine never sees latency, only the position it is asked to draw.
        a, b = self.make(), self.make()
        a.seek(130.0)
        b.seek(130.0)
        fa, fb = Frame(60), Frame(60)
        a.render(fa, 130.0, 0.025)
        b.render(fb, 130.0, 0.025)
        self.assertEqual(fa.pixels, fb.pixels)


def midi_bytes(ppq, events):
    """A tiny format-0 SMF writer for tests. events: (tick, raw bytes)."""
    body, last = b"", 0
    for tick, raw in sorted(events, key=lambda e: e[0]):
        delta, out = tick - last, bytearray()
        out.insert(0, delta & 0x7F)
        delta >>= 7
        while delta:
            out.insert(0, (delta & 0x7F) | 0x80)
            delta >>= 7
        body += bytes(out) + raw
        last = tick
    body += b"\x00\xff\x2f\x00"
    return b"MThd" + struct.pack(">IHHH", 6, 0, 1, ppq) + b"MTrk" + struct.pack(">I", len(body)) + body


class MidiCompilerTests(unittest.TestCase):
    def test_notes_markers_and_tempo_become_cues(self):
        ppq = 480
        events = [
            (0, b"\xff\x51\x03" + (500000).to_bytes(3, "big")),            # 120 BPM
            (0, b"\xff\x03\x04base"),
            (ppq * 4, b"\xff\x06\x06Chorus"),
            (ppq * 4, b"\x90\x24\x64"), (ppq * 12, b"\x80\x24\x00"),       # note 36: go
            (ppq * 5, b"\x90\x3c\x40"), (ppq * 6, b"\x80\x3c\x00"),        # note 60: fire, 1 beat
        ]
        patch = {"song": BASE["song"], "first_beat": 1.0, "tracks": BASE["tracks"],
                 "palettes": BASE["palettes"], "presets": BASE["presets"],
                 "notes": {"36": {"op": "go", "preset": "dots"},
                           "60": {"op": "fire", "pattern": "comet"}}}
        data, warnings = compile_midi(midi_bytes(ppq, events), patch)
        self.assertEqual(warnings, [])
        self.assertEqual(data["markers"], [{"at": "2|1|0", "name": "Chorus"}])
        sheet = compile_cuesheet(data)
        self.assertEqual(sheet.warnings, [])
        go, fire = sheet.cues
        self.assertAlmostEqual(go.time, 3.0)       # tick 4 beats = bar 2 = 1.0 + 2 s
        self.assertAlmostEqual(fire.time, 3.5)
        self.assertAlmostEqual(fire.dur, 0.5)      # one beat at 120 BPM


if __name__ == "__main__":
    unittest.main()
