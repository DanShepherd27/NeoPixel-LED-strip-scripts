"""Artist-inspired stage looks (arcade/stage): sections, phrasing and flash safety."""

import types
import unittest

from arcade.song.rhythm import BeatContext
from arcade.stage import LOOKS, create_look
from arcade.stage.ambient import AMBIENT_EFFECTS
from arcade.stage.cues import Arrangement
from led.frame import Frame

FPS = 40


def song_frames(name, section, bpm=128, bars=16):
    """Render a look pinned to ``section`` on an exact grid, like a song show."""
    look, ctx, period = create_look(name, section), BeatContext(), 60.0 / bpm
    length, frames, last = bars * 4 * period, [], None
    for step in range(int(length * FPS)):
        t = step / FPS
        ctx.t, ctx.dt, ctx.beat = t, 1.0 / FPS, t / period
        index = int(ctx.beat)
        ctx.new_beat = last is not None and index != last
        ctx.new_bar = ctx.new_beat and index % 4 == 0
        last = index
        ctx.beat_index, ctx.phase, ctx.beat_in_bar = index, ctx.beat - index, index % 4
        ctx.bar_in_section, ctx.progress, ctx.accent = index // 4, t / length, 0.8
        ctx.level, ctx.bands = 0.5, [0.5, 0.4, 0.3, 0.4, 0.3, 0.2]
        frame = Frame(60)
        look.render(frame, ctx)
        frames.append((t, list(frame.pixels)))
    return frames


def flashes_per_second(frames):
    """Most large-area flash starts (a quarter of the strip up by 0.3) in one second."""
    starts, previous, rising = [], None, False
    for t, pixels in frames:
        level = [max(p) / 255.0 for p in pixels]
        large = previous is not None and sum(
            1 for now, before in zip(level, previous) if now - before >= 0.3) >= len(level) / 4
        if large and not rising:
            starts.append(t)
        previous, rising = level, large
    return max((sum(1 for s in starts if start <= s < start + 1.0) for start in starts), default=0)


class StageLookTests(unittest.TestCase):
    def test_every_section_lights_the_strip_within_the_flash_limit(self):
        for name in LOOKS:
            for section in ("breakdown", "build", "drop"):
                for bpm in (100, 128, 175):
                    with self.subTest(look=name, section=section, bpm=bpm):
                        frames = song_frames(name, section, bpm)
                        self.assertTrue(any(any(max(p) for p in pixels) for _, pixels in frames))
                        self.assertLessEqual(flashes_per_second(frames), 3)

    def test_darkness_is_the_canvas(self):
        # Outside a drop most of the strip stays dark: contrast keeps the drop big.
        for name in LOOKS:
            with self.subTest(look=name):
                frames = song_frames(name, "breakdown")
                lit = [sum(1 for p in pixels if max(p) > 64) / 60.0 for _, pixels in frames]
                self.assertLess(sum(lit) / len(lit), 0.5)

    def test_build_ends_in_a_breath_of_darkness(self):
        for name in LOOKS:
            with self.subTest(look=name):
                *_, (t, last) = song_frames(name, "build", bars=4)
                self.assertTrue(all(p == (0, 0, 0) for p in last))

    def test_drop_lands_with_one_reveal(self):
        for name in LOOKS:
            with self.subTest(look=name):
                frames = song_frames(name, "drop")
                color = LOOKS[name].reveal_color
                first = frames[0][1]
                near = [p for p in first if max(abs(a - b) for a, b in zip(p, color)) < 40]
                self.assertGreater(len(near), 40)   # the whole strip in the reveal color

    def test_paradise_phrase_is_one_color(self):
        # Red phrase: red with white accents only, so green equals blue everywhere.
        frames = song_frames("paradise", "drop", bars=8)
        for t, pixels in frames:
            if t > 0.4:   # after the amber reveal
                self.assertTrue(all(p[1] == p[2] for p in pixels), "off-palette at %.2fs" % t)

    def test_live_arrangement_follows_the_kick(self):
        arrangement = Arrangement()
        cues = types.SimpleNamespace(dt=1.0 / FPS, level=0.2, kick_heard=False, period=0.5)
        for _ in range(6 * FPS):            # a pad with no kick: breakdown
            arrangement.update(cues)
        self.assertEqual(arrangement.section, "breakdown")
        cues.level = 0.6
        for _ in range(2 * FPS):            # a riser swelling louder: build
            arrangement.update(cues)
        self.assertEqual(arrangement.section, "build")
        cues.kick_heard = True              # the kick returns: drop, with the reveal
        arrangement.update(cues)
        self.assertEqual(arrangement.section, "drop")
        self.assertAlmostEqual(arrangement.reveal, 1.0, delta=0.1)

    def test_idle_ambients_render_without_beats(self):
        for name, factory in AMBIENT_EFFECTS:
            with self.subTest(effect=name):
                effect, frame = factory(60), Frame(60)
                for _ in range(4 * FPS):
                    effect.render(frame, 1.0 / FPS)
                self.assertTrue(any(max(p) for p in frame.pixels))


if __name__ == "__main__":
    unittest.main()
