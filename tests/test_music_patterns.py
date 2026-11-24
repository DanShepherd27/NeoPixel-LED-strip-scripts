"""Live music patterns driven by a synthetic drum loop (kick every beat, snare on 2 and 4)."""

import types
import unittest
from unittest import mock

import arcade.music_rendering as music_rendering
from arcade.music_animations import MUSIC_ANIMATIONS as PATTERNS
import led.web_audio as web_audio
from arcade.manager import ArcadeManager
from led.frame import Frame

FPS = 40


def play(pattern, bpm=120, seconds=12.0):
    """Render ``pattern`` against a drum loop; returns ``[(t, beat_in_bar, locked, pixels)]``."""
    clock = [1000.0]
    fake_time = types.SimpleNamespace(monotonic=lambda: clock[0])
    with mock.patch.object(music_rendering, "time", fake_time), \
            mock.patch.object(web_audio, "time", fake_time):
        manager = ArcadeManager(count=60)
        manager.start_music_mode()
        manager.music_animation = pattern
        token = manager.web_mics.request("test-client-1", "Tester")["token"]
        period = 60.0 / bpm
        frame, frames = Frame(60), []
        for step in range(int(seconds * FPS)):
            clock[0] += 1.0 / FPS
            t = clock[0] - 1000.0
            beat, phase = divmod(t / period, 1.0)
            on_beat = phase < 1.0 / FPS / period
            manager.web_mics.update(token, 0.55, 0.6, False, [0.5, 0.45, 0.4, 0.35, 0.3, 0.25], 0, hits={
                "kick": 0.95 if on_beat else 0.12, "kick_ago_ms": 0,
                "snare": 0.95 if on_beat and int(beat) % 2 else 0.12, "snare_ago_ms": 0,
            })
            frame.clear()
            manager.render(frame, 1.0 / FPS)
            ctx = manager._music_ctx
            frames.append((t, ctx.beat_in_bar, ctx.locked, list(frame.pixels)))
        return frames


def most_flashes_per_second(frames):
    """Most large-area flash starts (a quarter of the strip up by 0.3) in one second."""
    starts, previous, rising = [], None, False
    for t, _, _, pixels in frames:
        intensity = [max(p) / 255.0 for p in pixels]
        large = previous is not None and sum(
            1 for now, before in zip(intensity, previous) if now - before >= 0.3) >= len(intensity) / 4
        if large and not rising:
            starts.append(t)
        previous, rising = intensity, large
    return max((sum(1 for s in starts if start <= s < start + 1.0) for start in starts), default=0)


class LivePatternTests(unittest.TestCase):
    def test_every_pattern_renders_and_lights_the_strip(self):
        for pattern in PATTERNS:
            with self.subTest(pattern=pattern):
                frames = play(pattern, seconds=4.0)
                self.assertTrue(any(any(max(p) for p in pixels) for *_, pixels in frames))

    def test_no_pattern_exceeds_three_large_flashes_per_second(self):
        for pattern in PATTERNS:
            with self.subTest(pattern=pattern):
                self.assertLessEqual(most_flashes_per_second(play(pattern, bpm=175)), 3)

    def test_snare_lights_the_ends_and_the_kick_does_not(self):
        frames = play("center_pulse", seconds=12.0)
        snare_ends, kick_ends = [], []
        for t, beat_in_bar, locked, pixels in frames:
            if t < 8 or not locked:
                continue
            phase = (t / 0.5) % 1.0
            if phase < 0.06:   # the first frames of a beat, while its accent shows
                end = max(max(pixels[0]), max(pixels[-1]))
                (snare_ends if beat_in_bar % 2 else kick_ends).append(end)
        self.assertTrue(snare_ends and kick_ends)
        self.assertGreater(min(snare_ends), 90)
        self.assertLess(max(kick_ends), 40)


if __name__ == "__main__":
    unittest.main()
