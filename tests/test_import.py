"""Tests for the song importer and show generator: python -m unittest discover tests"""

import sys
import tempfile
import time
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arcade.song.cuesheet import compile_cuesheet  # noqa: E402
from arcade.song.importer import ImportJobs, slugify  # noqa: E402
from arcade.song.showgen import generate_show  # noqa: E402

try:
    import numpy as np
except ImportError:  # the analyzer needs numpy; the Pi has it, a bare checkout may not
    np = None

BPM, SAMPLE_RATE = 128.0, 22050
BEAT, BAR = 60 / BPM, 4 * 60 / BPM
# (bars, instruments, gain): intro, drop 1, breakdown, build, drop 2, outro
PLAN = [(16, "kick hat", .5), (32, "kick bass hat clap", 1.0), (12, "pad", .8), (4, "pad riser", .8),
        (32, "kick bass hat clap pad", 1.0), (12, "kick hat", .3)]


def synth_techno(path, first_kick=0.37):
    """A tiny four-on-the-floor track with a known arrangement."""
    rng = np.random.default_rng(0)
    total = sum(bars for bars, _, _ in PLAN)
    out = np.zeros(int((total * BAR + 2) * SAMPLE_RATE))

    def add(start, sound, gain):
        index = int(start * SAMPLE_RATE)
        out[index:index + len(sound)] += gain * sound[:len(out) - index]
    t = np.arange(int(0.25 * SAMPLE_RATE)) / SAMPLE_RATE
    kick = np.sin(2 * np.pi * (50 + 110 * np.exp(-t * 30)) * t) * np.exp(-t * 9)
    noise = rng.standard_normal(int(0.1 * SAMPLE_RATE))
    hat = noise[:int(0.05 * SAMPLE_RATE)] * np.exp(-np.arange(int(0.05 * SAMPLE_RATE)) / SAMPLE_RATE * 80) * .25
    clap = noise * np.exp(-np.arange(len(noise)) / SAMPLE_RATE * 35) * .5
    bar_index = 0
    for bars, instruments, gain in PLAN:
        parts = instruments.split()
        for bar in range(bars):
            start = first_kick + (bar_index + bar) * BAR
            for k in range(4):
                beat_time = start + k * BEAT
                if "kick" in parts:
                    add(beat_time, kick, gain)
                if "hat" in parts:
                    add(beat_time + BEAT / 2, hat, gain)
                if "clap" in parts and k in (1, 3):
                    add(beat_time, clap, gain)
            if "pad" in parts:
                tp = np.arange(int(BAR * SAMPLE_RATE)) / SAMPLE_RATE
                add(start, (np.sin(2 * np.pi * 220 * tp) + np.sin(2 * np.pi * 330 * tp)) * .1, gain)
        bar_index += bars
    out /= np.abs(out).max() * 1.05
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes((out * 32767).astype(np.int16).tobytes())


@unittest.skipIf(np is None, "numpy not installed")
class GeneratorTests(unittest.TestCase):
    def test_finds_tempo_downbeat_and_sections_of_a_techno_track(self):
        import json
        from arcade.song.analysis import SongAnalysis
        from arcade.song.analyzer import analyze_file
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = Path(tmp) / "techno.wav"
            synth_techno(wav_path)
            analysis_path = Path(tmp) / "techno.analysis.json"
            analysis_path.write_text(json.dumps(analyze_file(wav_path, tmp)))
            analysis = SongAnalysis(analysis_path)
        self.assertAlmostEqual(analysis.tempo["bpm"], BPM, delta=0.3)
        beat_error = (analysis.tempo["offset"] - 0.37) % BEAT
        self.assertLess(min(beat_error, BEAT - beat_error), 0.03)   # on the kick, not the off-beat hat
        show = generate_show(analysis, {"id": "t", "title": "T", "audio": "t.mp3", "analysis": "t.json"})
        names = [m["name"].split(" (")[0] for m in show["markers"]]
        self.assertEqual(names, ["Intro", "Drop 1", "Drop 1", "Breakdown 1", "Build 1", "Drop 2", "Drop 2", "Outro"])
        bars = [int(m["at"].split("|")[0]) for m in show["markers"]]
        for found, expected in zip(bars, [1, 17, 33, 49, 61, 65, 81, 97]):
            self.assertAlmostEqual(found, expected, delta=1)
        sheet = compile_cuesheet(show)
        self.assertEqual(sheet.warnings, [])


class JobTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("  Déjà Vu (Remix)! "), "d-j-vu-remix")
        self.assertEqual(slugify("!!!"), "song")

    def make_jobs(self, tmp, lines):
        def spawn(audio, folder, job):
            yield from lines
        return ImportJobs(Path(tmp) / "songs", spawn)

    def wait(self, jobs, status):
        for _ in range(100):
            if jobs.snapshot() and jobs.snapshot()[-1]["status"] == status:
                return
            time.sleep(0.02)
        self.fail("job never became %s: %s" % (status, jobs.snapshot()))

    def upload(self, tmp, data=b"ID3\x03\x00\x00\x00\x00\x00\x00"):
        path = Path(tmp) / "up.mp3"
        path.write_bytes(data)
        return path

    def test_progress_then_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = self.make_jobs(tmp, ["PROGRESS 0.400 Finding the tempo\n", "DONE\n"])
            job = jobs.add(self.upload(tmp), "My Song.mp3")
            self.assertEqual(job["id"], "my-song")
            self.wait(jobs, "ready")
            self.assertTrue((Path(tmp) / "songs" / "my-song" / "my-song.mp3").exists())

    def test_failed_analysis_cleans_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = self.make_jobs(tmp, ["ERROR could not decode the audio\n"])
            jobs.add(self.upload(tmp), "bad.mp3")
            self.wait(jobs, "error")
            self.assertIn("decode", jobs.snapshot()[-1]["message"])
            time.sleep(0.1)
            self.assertFalse((Path(tmp) / "songs" / "bad").exists())

    def test_rejects_non_mp3_and_duplicate_names_get_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = self.make_jobs(tmp, ["DONE\n"])
            with self.assertRaises(ValueError):
                jobs.add(self.upload(tmp, b"RIFF....WAVE"), "x.wav")
            first = jobs.add(self.upload(tmp), "Same.mp3")
            self.wait(jobs, "ready")
            second = jobs.add(self.upload(tmp), "Same.mp3")
            self.assertEqual((first["id"], second["id"]), ("same", "same-2"))

    def test_delete_only_removes_uploaded_songs(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = self.make_jobs(tmp, ["DONE\n"])
            jobs.add(self.upload(tmp), "Gone.mp3")
            self.wait(jobs, "ready")
            self.assertFalse(jobs.delete("../../etc"))
            self.assertTrue(jobs.delete("gone"))
            self.assertFalse(jobs.delete("gone"))


if __name__ == "__main__":
    unittest.main()
