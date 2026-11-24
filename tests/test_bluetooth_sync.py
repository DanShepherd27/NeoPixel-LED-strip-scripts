"""Live Bluetooth delay tracking (arcade/bluetooth_sync.py) with a synthetic stream and mic."""

import random
import unittest

from arcade.bluetooth_sync import FIRST_SECONDS, INTERVAL_SECONDS, BluetoothDelaySync
from arcade.song.latency import estimate_latency
from led.audio_sources import BluetoothSource

CHUNK = 0.023      # seconds per analyzed chunk, like the Bluetooth capture
FPS = 40


def music_envelope(seconds, seed=1):
    """Loudness chunks of a beat-driven track: kicks at 128 BPM with varied accents."""
    rng, beat, chunks = random.Random(seed), 60.0 / 128.0, []
    accents = [rng.uniform(0.3, 1.0) for _ in range(int(seconds / beat) + 2)]
    t = 0.0
    while t < seconds:
        index, phase = divmod(t / beat, 1.0)
        chunks.append((t + CHUNK, 300.0 + 3000.0 * accents[int(index)] * (1.0 - phase) ** 4, CHUNK))
        t += CHUNK
    return chunks


class Recording:
    """A capture whose history only reveals chunks that have arrived by ``clock()``."""

    def __init__(self, chunks, clock, status="listening"):
        self.chunks, self.clock, self.status = chunks, clock, status
        self.enabled = []
        self.recording_since = None   # set for the mic: it records only while enabled

    def history_since(self, start):
        now = self.clock()
        since = self.recording_since if self.recording_since is not None else -1.0
        return [chunk for chunk in self.chunks if max(start, since) <= chunk[0] <= now]

    def snapshot(self):
        return {"status": self.status}

    def set_enabled(self, enabled):
        self.enabled.append(enabled)
        if enabled:
            self.recording_since = self.clock()


class Immediate:
    """Runs the estimator synchronously instead of on a background thread."""

    def __init__(self, *args):
        self.result = estimate_latency(*args)


def setup(speaker_delay, mic_gain=0.3, noise=40.0, seconds=60.0, enabled=True):
    clock = [0.0]
    stream_chunks = music_envelope(seconds)
    rng = random.Random(7)
    mic_chunks = [(arrival + speaker_delay, rms * mic_gain + rng.uniform(0, noise), duration)
                  for arrival, rms, duration in stream_chunks]
    now = lambda: clock[0]   # noqa: E731
    stream, mic = Recording(stream_chunks, now), Recording(mic_chunks, now)
    learned = []
    sync = BluetoothDelaySync(stream, mic, enabled, on_learned=learned.append,
                              clock=now, measure=Immediate)
    return clock, sync, stream, mic, learned


def run(clock, sync, delay_ms, seconds):
    for _ in range(int(seconds * FPS)):
        clock[0] += 1.0 / FPS
        delay_ms = sync.update(delay_ms)
    return delay_ms


class BluetoothDelaySyncTests(unittest.TestCase):
    def test_finds_the_speaker_delay_then_holds_it(self):
        clock, sync, _, mic, learned = setup(speaker_delay=0.42)
        sync.start()
        self.assertEqual(mic.enabled, [True])          # the Pi microphone starts listening
        delay = run(clock, sync, 300, FIRST_SECONDS + 0.5)
        self.assertAlmostEqual(delay, 420, delta=15)   # first match jumps straight there
        delay = run(clock, sync, delay, 6 * INTERVAL_SECONDS)
        self.assertAlmostEqual(delay, 420, delta=15)
        self.assertEqual(sync.describe()["state"], "locked")
        sync.stop()
        self.assertEqual(mic.enabled, [True, False])
        self.assertTrue(learned)
        self.assertAlmostEqual(learned[-1], 420, delta=15)

    def test_tracks_a_slowly_changing_delay_in_small_steps(self):
        clock, sync, _, _, _ = setup(speaker_delay=0.42)
        sync.start()
        delay = run(clock, sync, 300, FIRST_SECONDS + 0.5)
        # same stream, but the speakers fall 80 ms further behind
        sync.mic.chunks = [(a + 0.08, r, d) for a, r, d in sync.mic.chunks]
        after_one = run(clock, sync, delay, INTERVAL_SECONDS)
        self.assertLessEqual(after_one - delay, 31)    # one step is at most 30 ms
        settled = run(clock, sync, after_one, 15 * INTERVAL_SECONDS)
        self.assertAlmostEqual(settled, 500, delta=20)

    def test_room_noise_leaves_the_delay_alone(self):
        clock, sync, _, mic, _ = setup(speaker_delay=0.42)
        rng = random.Random(3)
        mic.chunks = [(a, rng.uniform(0, 400), d) for a, _, d in mic.chunks]
        sync.start()
        self.assertEqual(run(clock, sync, 300, FIRST_SECONDS + 4 * INTERVAL_SECONDS), 300)
        self.assertEqual(sync.describe()["state"], "weak")

    def test_off_when_disabled_or_no_stream(self):
        clock, sync, stream, mic, _ = setup(speaker_delay=0.42, enabled=False)
        sync.start()
        self.assertEqual(mic.enabled, [])
        self.assertEqual(run(clock, sync, 300, 20), 300)
        sync.enabled = True
        stream.status = "waiting"
        self.assertEqual(run(clock, sync, 300, 20), 300)
        self.assertEqual(sync.describe()["state"], "waiting")

    def test_bluetooth_source_drives_the_sync(self):
        class FakeSync:
            def __init__(self):
                self.calls = []

            def start(self):
                self.calls.append("start")

            def stop(self):
                self.calls.append("stop")

            def update(self, delay_ms):
                return delay_ms + 10

            def describe(self):
                return {"enabled": True, "state": "locked", "score": 0.9}

        class FakeCapture:
            def set_enabled(self, enabled):
                pass

            def snapshot(self):
                return {"level": 0.0, "peak": 0.0, "bands": [0.0] * 6, "clap": False}

            def take_onsets(self):
                return []

        fake = FakeSync()
        source = BluetoothSource(FakeCapture(), 300, fake)
        source.activate()
        source.features()
        self.assertEqual(source.delay_ms, 310)
        self.assertEqual(source.describe()["sync"]["state"], "locked")
        source.deactivate()
        self.assertEqual(fake.calls, ["start", "stop"])


if __name__ == "__main__":
    unittest.main()
