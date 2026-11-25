"""The FX intensity knob and volume dynamics: stage looks must
visibly hit on the beat, follow the music's loudness, and hit harder with the knob up."""

import types
import unittest
from unittest import mock

import arcade.music_rendering as music_rendering
import led.web_audio as web_audio
from arcade.manager import ArcadeManager
from arcade.music_dynamics import Dynamics
from led.frame import Frame

FPS, BPM = 40, 124
FX_PATTERNS = ("genesys", "holo", "paradise", "rave")


def measure(pattern, fx, seconds=12.0):
    """Mean brightness right after beats, late in beats, and in loud vs quiet stretches.
    The drum loop alternates 4 s loud and 4 s quiet."""
    clock = [1000.0]
    fake_time = types.SimpleNamespace(monotonic=lambda: clock[0])
    with mock.patch.object(music_rendering, "time", fake_time), \
            mock.patch.object(web_audio, "time", fake_time):
        manager = ArcadeManager(count=60)
        manager.start_music_mode()
        manager.music_animation, manager.music_fx_intensity = pattern, fx
        token = manager.web_mics.request("test-client-1", "Tester")["token"]
        period, frame = 60.0 / BPM, Frame(60)
        groups = {"beat": [], "gap": [], "loud": [], "quiet": []}
        for _ in range(int(seconds * FPS)):
            clock[0] += 1.0 / FPS
            t = clock[0] - 1000.0
            beat, phase = divmod(t / period, 1.0)
            on_beat = phase < 1.0 / FPS / period
            loud = int(t / 4) % 2 == 1
            level = (0.6 if loud else 0.25) * (1.0 if phase < 0.2 else 0.6)
            manager.web_mics.update(token, level, level, False, [level] * 6, 0, hits={
                "kick": 0.95 if on_beat else 0.1, "kick_ago_ms": 0,
                "snare": 0.95 if on_beat and int(beat) % 2 else 0.1, "snare_ago_ms": 0,
            })
            frame.clear()
            manager.render(frame, 1.0 / FPS)
            if t < 6.0:
                continue
            values = [max(p) / 255.0 for p in frame.pixels]
            value = sum(values) / len(values)
            if phase < 0.12:
                groups["beat"].append(value)
            elif phase > 0.7:
                groups["gap"].append(value)
            groups["loud" if loud else "quiet"].append(value)
        return {name: sum(v) / len(v) for name, v in groups.items()}


class FxIntensityTests(unittest.TestCase):
    def test_beats_stand_out_and_the_knob_makes_them_stand_out_more(self):
        for pattern in FX_PATTERNS:
            with self.subTest(pattern=pattern):
                normal, strong = measure(pattern, 100), measure(pattern, 200)
                self.assertGreater(normal["beat"], 2.4 * normal["gap"])
                self.assertGreater(strong["beat"] / strong["gap"], normal["beat"] / normal["gap"])

    def test_loud_stretches_are_brighter_than_quiet_ones(self):
        for pattern in FX_PATTERNS:
            with self.subTest(pattern=pattern):
                result = measure(pattern, 100)
                self.assertGreater(result["loud"], 1.1 * result["quiet"])

    def test_zero_intensity_still_renders(self):
        for pattern in FX_PATTERNS:
            with self.subTest(pattern=pattern):
                self.assertGreater(measure(pattern, 0)["loud"], 0.0)


class DynamicsTests(unittest.TestCase):
    def test_energy_is_relative_to_the_recent_ceiling(self):
        dynamics = Dynamics()
        for _ in range(4 * FPS):
            dynamics.update(0.8, 1.0 / FPS)
        self.assertGreater(dynamics.energy, 0.9)
        for _ in range(FPS):
            dynamics.update(0.3, 1.0 / FPS)
        self.assertLess(dynamics.energy, 0.5)       # a quiet passage after a loud one

    def test_surge_fires_on_a_jump_and_fades(self):
        dynamics = Dynamics()
        for _ in range(2 * FPS):
            dynamics.update(0.2, 1.0 / FPS)
        self.assertLess(dynamics.surge, 0.05)
        for _ in range(3):
            dynamics.update(0.8, 1.0 / FPS)
        self.assertGreater(dynamics.surge, 0.8)
        for _ in range(FPS):
            dynamics.update(0.8, 1.0 / FPS)
        self.assertLess(dynamics.surge, 0.2)


if __name__ == "__main__":
    unittest.main()
