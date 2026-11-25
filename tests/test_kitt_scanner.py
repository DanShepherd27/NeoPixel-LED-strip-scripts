"""The KITT pattern: a steady comet scanner in a middle window that ignores sound, and
a three-bar voice box (middle bar longest) that opens from the bars' centres with sound."""

import unittest

from arcade.kitt_scanner import KittScanner, Layout, Scanner, VoiceBox
from led.frame import Frame

FPS = 40


def run(level, seconds=2.0, intensity=1.0, count=60):
    kitt, frame = KittScanner(), Frame(count)
    for _ in range(int(seconds * FPS)):
        kitt.render(frame, level, [level] * 6, 1.0 / FPS, intensity)
    return kitt, [pixel[0] / 255.0 for pixel in frame.pixels]


def lit(values, first, last, threshold=0.05):
    return sum(1 for value in values[first:last] if value > threshold)


class LayoutTests(unittest.TestCase):
    def test_window_is_centred_and_middle_bar_is_longest(self):
        layout = Layout(60)
        self.assertEqual((layout.window_start, layout.window), (18, 24))
        middle, *outer = layout.bars
        self.assertEqual(len(outer), 2)
        self.assertTrue(all(half < middle[1] for _, half, _ in outer))


class ScannerTests(unittest.TestCase):
    def test_head_reaches_both_ends_and_stays_in_the_window(self):
        scanner, positions = Scanner(24), []
        for _ in range(4 * FPS):
            scanner.update(1.0 / FPS)
            positions.append(scanner.position())
        self.assertEqual(min(positions), 0.0)
        self.assertEqual(max(positions), 23.0)

    def test_tail_fades_behind_the_head(self):
        scanner = Scanner(24)
        for _ in range(int(0.5 * FPS)):    # mid-way through the first pass
            glow = scanner.update(1.0 / FPS)
        head = int(scanner.position())
        tail = glow[head - 6:head + 1]
        self.assertGreater(glow[head], 0.7)
        self.assertEqual(tail, sorted(tail))        # dimmer the further behind
        self.assertLess(glow[head - 6], 0.3)
        self.assertTrue(all(value < 0.05 for value in glow[head + 3:]))   # nothing ahead


class VoiceBoxTests(unittest.TestCase):
    def test_silence_shows_only_the_scanner(self):
        _, values = run(0.0)
        self.assertEqual(lit(values, 0, 18) + lit(values, 42, 60), 0)
        self.assertGreater(max(values[18:42]), 0.9)

    def test_sound_opens_the_outer_bars_from_their_centres(self):
        _, values = run(0.6)
        lower = [index for index in range(16) if values[index] > 0.05]
        self.assertTrue(lower)
        self.assertAlmostEqual((min(lower) + max(lower)) / 2.0, 7.5, delta=1.0)
        self.assertEqual(lit(values, 0, 16), lit(values, 44, 60))   # mirrored

    def test_scanner_head_stays_the_brightest_point(self):
        _, values = run(0.8)
        self.assertGreater(max(values[18:42]), max(values[:18] + values[42:]))

    def test_quiet_after_loud_closes_the_bars(self):
        box = VoiceBox()
        for _ in range(3 * FPS):
            box.update(0.8, 1.0 / FPS)
        loud = box.opening
        for _ in range(FPS):
            box.update(0.25, 1.0 / FPS)
        self.assertGreater(loud, 0.9)
        self.assertLess(box.opening, 0.5 * loud)

    def test_more_intensity_keeps_soft_sounds_closed(self):
        soft = {}
        for intensity in (0.0, 1.0, 2.0):
            box = VoiceBox()
            for _ in range(3 * FPS):
                box.update(0.8, 1.0 / FPS, intensity)
            for _ in range(FPS):
                box.update(0.4, 1.0 / FPS, intensity)
            soft[intensity] = box.opening
        self.assertGreater(soft[0.0], soft[1.0])
        self.assertGreater(soft[1.0], soft[2.0])

    def test_bars_open_gradually_from_silence(self):
        box = VoiceBox()
        for _ in range(FPS):
            box.update(0.0, 1.0 / FPS)
        box.update(1.0, 1.0 / FPS)
        self.assertLessEqual(box.opening, VoiceBox.RISE_PER_SECOND / FPS + 1e-9)

    def test_short_strips_render(self):
        for count in (8, 12, 30, 61):
            with self.subTest(count=count):
                _, values = run(0.5, seconds=0.5, count=count)
                self.assertEqual(len(values), count)
                self.assertGreater(max(values), 0.0)


if __name__ == "__main__":
    unittest.main()
