import random
import unittest

from arcade.live_beat import ENVELOPE_RATE, LiveBeatTracker, estimate_period

FRAME = 1.0 / 40


def drum_samples(bpm, seconds, kick_beats=(0, 1, 2, 3), snare_beats=(1, 3),
                 chunk=0.032, jitter=0.0, seed=1):
    """Pi-style onset samples every ``chunk`` seconds: strong on hits, noise between."""
    rng = random.Random(seed)
    period = 60.0 / bpm
    hits = []
    beat = 0
    while beat * period < seconds:
        if beat % 4 in kick_beats:
            hits.append((beat * period + rng.uniform(-jitter, jitter), "kick"))
        if beat % 4 in snare_beats:
            hits.append((beat * period + rng.uniform(-jitter, jitter), "snare"))
        beat += 1
    samples = []
    t = 0.0
    while t < seconds:
        for name in ("kick", "snare"):
            strength = rng.uniform(0.05, 0.25)
            if any(name == hit_name and t <= hit < t + chunk for hit, hit_name in hits):
                strength = rng.uniform(0.8, 1.0)
            samples.append((t, name, strength))
        t += chunk
    return samples


def run(tracker, samples, seconds, start=100.0):
    """Feed samples as a 40 FPS renderer would, return contexts per frame."""
    samples = sorted((start + t, name, s) for t, name, s in samples)
    frames = []
    index = 0
    now = start
    while now < start + seconds:
        now += FRAME
        batch = []
        while index < len(samples) and samples[index][0] <= now:
            batch.append(samples[index])
            index += 1
        ctx = tracker.update(now, batch, [0.0] * 6, 0.5, FRAME)
        frames.append((now - start, ctx.beat, ctx.locked, ctx.beat_in_bar,
                       ctx.bar_known, ctx.backbeat_known, ctx.pulse, ctx.snare_pulse))
    return frames


class TempoTest(unittest.TestCase):
    def test_estimate_is_finer_than_one_envelope_bin(self):
        for bpm in (96.0, 124.0, 128.0, 140.0):
            period = 60.0 / bpm
            envelope = [0.0] * (8 * ENVELOPE_RATE)
            beat = 0.0
            while beat < len(envelope):
                envelope[int(beat)] = 1.0
                beat += period * ENVELOPE_RATE
            found, strength = estimate_period(envelope)
            self.assertAlmostEqual(60.0 / found, bpm, delta=bpm * 0.015, msg=bpm)
            self.assertGreater(strength, 0.1)


class TrackerTest(unittest.TestCase):
    def test_locks_to_four_on_the_floor_with_backbeat_snare(self):
        tracker = LiveBeatTracker()
        frames = run(tracker, drum_samples(128, 20, jitter=0.01), 20)
        self.assertTrue(frames[-1][2], "should be locked")
        self.assertAlmostEqual(tracker.ctx.bpm, 128, delta=1.5)
        period = 60.0 / 128
        # Beats land on the kicks: shortly after a kick the phase is near zero.
        late = [f for f in frames if f[0] > 12]
        for t, beat, *_ in late[::7]:
            phase_drift = (beat - t / period) % 1.0
            self.assertLess(min(phase_drift, 1 - phase_drift), 0.12, (t, beat))
        # Snares land on beats 2 and 4 of the bar (indexes 1 and 3).
        self.assertTrue(frames[-1][5], "backbeat should be known")
        for t, beat, locked, beat_in_bar, *_ in late:
            position = t / period
            if 0.2 < position % 1.0 < 0.5:   # well inside a beat
                self.assertEqual(beat_in_bar % 2, int(position) % 2, t)

    def test_rock_beat_finds_downbeat(self):
        tracker = LiveBeatTracker()
        frames = run(tracker, drum_samples(100, 24, kick_beats=(0, 2), jitter=0.008), 24)
        self.assertTrue(frames[-1][2])
        self.assertTrue(frames[-1][4], "bar should be known")
        period = 0.6
        late = [f for f in frames if f[0] > 16]
        for t, beat, locked, beat_in_bar, *_ in late:
            position = t / period
            if 0.2 < position % 1.0 < 0.5:
                self.assertEqual(beat_in_bar, int(position) % 4, t)

    def test_one_pulse_per_beat(self):
        tracker = LiveBeatTracker()
        frames = run(tracker, drum_samples(120, 16), 16)
        pops = 0
        previous = 0.0
        for t, beat, locked, _, _, _, pulse, _ in frames:
            if t > 10 and pulse > 0.5 and previous <= 0.5:
                pops += 1
            if t > 10:
                previous = pulse
        self.assertAlmostEqual(pops, 12, delta=1)   # 6 s at 120 BPM

    def test_unlocks_in_silence(self):
        tracker = LiveBeatTracker()
        run(tracker, drum_samples(120, 12), 12)
        self.assertTrue(tracker.ctx.locked)
        quiet = [(t, name, 0.05) for t, name, _ in drum_samples(120, 6)]
        run(tracker, quiet, 6, start=112.0)
        self.assertFalse(tracker.ctx.locked)


if __name__ == "__main__":
    unittest.main()


class NoisyMusicTest(unittest.TestCase):
    def test_browser_packets_with_ghost_notes_and_tempo_change(self):
        """Browser-style packets (strongest onset per 50 ms) with timing noise,
        off-beat ghost kicks, and a tempo change from 118 to 132 BPM."""
        rng = random.Random(7)
        samples = []
        t = 0.0
        beat = 0
        while t < 40:
            period = 60.0 / (118 if t < 20 else 132)
            samples.append((t + rng.uniform(-0.012, 0.012), "kick", rng.uniform(0.75, 1.0)))
            if beat % 4 in (1, 3):
                samples.append((t + rng.uniform(-0.012, 0.012), "snare", rng.uniform(0.75, 1.0)))
            if rng.random() < 0.25:
                samples.append((t + period / 2, "kick", rng.uniform(0.5, 0.7)))
            for step in range(1, 10):
                quiet = t + step * period / 10
                samples.append((quiet, "kick", rng.uniform(0.05, 0.3)))
                samples.append((quiet, "snare", rng.uniform(0.05, 0.3)))
            t += period
            beat += 1
        tracker = LiveBeatTracker()
        run(tracker, [s for s in samples if s[0] < 20], 20)
        self.assertTrue(tracker.ctx.locked)
        self.assertAlmostEqual(tracker.ctx.bpm, 118, delta=2)
        run(tracker, [(s[0] - 20, s[1], s[2]) for s in samples if s[0] >= 20], 20, start=120.0)
        self.assertTrue(tracker.ctx.locked)
        self.assertAlmostEqual(tracker.ctx.bpm, 132, delta=2)
