"""Tests for the sound-reactive audio sources: python -m unittest discover tests"""

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arcade.manager import ArcadeManager  # noqa: E402
from led.audio_sources import (  # noqa: E402
    AudioSource, BluetoothSource, DelayedFeed, MicrophoneSource, SILENT,
)
from led.bluetooth_audio import BluetoothAudioInput, WAITING_MESSAGE  # noqa: E402
from led.pcm_sink import AplaySink, PcmSink  # noqa: E402


def features(level):
    return {"level": level, "peak": 0.0, "bands": [level] * 6, "clap": False}


class FakeCapture:
    """Stands in for AudioInput/BluetoothAudioInput."""

    def __init__(self):
        self.enabled = None
        self.level = 0.0
        self.onsets = []

    def set_enabled(self, enabled):
        self.enabled = enabled

    def snapshot(self):
        return dict(features(self.level), status="listening")

    def take_onsets(self):
        taken, self.onsets = self.onsets, []
        return taken


class FakeWebMics:
    def __init__(self):
        self.active = False
        self.onsets = []
        self.was_reset = False

    def snapshot(self):
        return dict(features(0.9), active=self.active)

    def take_onsets(self):
        taken, self.onsets = self.onsets, []
        return taken

    def reset(self):
        self.was_reset = True


class RecordingSink(PcmSink):
    def __init__(self):
        self.chunks = []
        self.started = self.closed = False

    def start(self):
        self.started = True

    def write(self, chunk):
        self.chunks.append(chunk)

    def close(self):
        self.closed = True


class DelayedFeedTests(unittest.TestCase):
    def test_no_delay_passes_everything_through(self):
        feed = DelayedFeed()
        shown, audible = feed.advance(10.0, features(0.5), [(9.99, "kick", 1.0)], 0.0)
        self.assertEqual(shown["level"], 0.5)
        self.assertEqual(audible, [(9.99, "kick", 1.0)])

    def test_features_and_onsets_wait_for_the_delay(self):
        feed = DelayedFeed()
        shown, audible = feed.advance(10.0, features(0.7), [(10.0, "kick", 0.8)], 0.3)
        self.assertEqual(shown, SILENT)
        self.assertEqual(audible, [])
        shown, audible = feed.advance(10.2, features(0.1), [], 0.3)
        self.assertEqual((shown, audible), (SILENT, []))
        shown, audible = feed.advance(10.31, features(0.2), [], 0.3)
        self.assertEqual(shown["level"], 0.7)
        self.assertEqual([(name, strength) for _, name, strength in audible], [("kick", 0.8)])
        self.assertAlmostEqual(audible[0][0], 10.3)   # stamped with when it is heard

    def test_clear_drops_pending_audio(self):
        feed = DelayedFeed()
        feed.advance(1.0, features(0.7), [(1.0, "snare", 1.0)], 0.5)
        feed.clear()
        self.assertEqual(feed.advance(2.0, features(0.0), [], 0.5), (SILENT, []))


class MicrophoneSourceTests(unittest.TestCase):
    def setUp(self):
        self.web, self.pi = FakeWebMics(), FakeCapture()
        self.source = MicrophoneSource(self.web, self.pi)

    def test_pi_microphone_listens_only_without_a_browser_microphone(self):
        self.source.activate()
        self.assertTrue(self.pi.enabled)
        self.web.active = True
        self.assertEqual(self.source.features()["level"], 0.9)
        self.assertFalse(self.pi.enabled)
        self.web.active = False
        self.source.features()
        self.assertTrue(self.pi.enabled)

    def test_onsets_come_from_the_microphone_in_use(self):
        self.web.onsets = [(1.0, "kick", 1.0)]
        self.pi.onsets = [(2.0, "snare", 1.0)]
        self.source.features()
        self.assertEqual(self.source.take_onsets(), [(2.0, "snare", 1.0)])
        self.web.active = True
        self.web.onsets = [(3.0, "kick", 1.0)]
        self.pi.onsets = [(4.0, "snare", 1.0)]
        self.source.features()
        self.assertEqual(self.source.take_onsets(), [(3.0, "kick", 1.0)])

    def test_deactivate_releases_both_microphones(self):
        self.source.activate()
        self.source.deactivate()
        self.assertFalse(self.pi.enabled)
        self.assertTrue(self.web.was_reset)

    def test_describe_names_the_microphone_in_use(self):
        self.assertEqual(self.source.describe()["source"], "pi")
        self.web.active = True
        self.assertEqual(self.source.describe()["source"], "web")


class BluetoothSourceTests(unittest.TestCase):
    def test_activation_controls_the_capture(self):
        capture = FakeCapture()
        source = BluetoothSource(capture)
        source.activate()
        self.assertTrue(capture.enabled)
        source.deactivate()
        self.assertFalse(capture.enabled)

    def test_lights_are_held_back_by_the_playback_delay(self):
        capture = FakeCapture()
        source = BluetoothSource(capture, delay_ms=150)
        capture.level = 0.8
        capture.onsets = [(time.monotonic(), "kick", 1.0)]
        self.assertEqual(source.features(), SILENT)
        self.assertEqual(source.take_onsets(), [])
        time.sleep(0.2)
        capture.level = 0.0
        self.assertEqual(source.features()["level"], 0.8)
        self.assertEqual([name for _, name, _ in source.take_onsets()], ["kick"])
        self.assertEqual(source.take_onsets(), [])

    def test_describe_reports_the_delay(self):
        description = BluetoothSource(FakeCapture(), delay_ms=250).describe()
        self.assertEqual((description["source"], description["delay_ms"]), ("bluetooth", 250))


class BluetoothAudioInputTests(unittest.TestCase):
    def setUp(self):
        self.sink = RecordingSink()
        self.capture = BluetoothAudioInput("bluealsa:PROFILE=a2dp", self.sink)

    def test_loud_digital_music_is_not_pinned_at_the_ceiling(self):
        level, peak, bands = self.capture._features(
            5000.0, 20000.0, 60.0, [0.2, 0.1, 0.05, 0.02, 0.01, 0.005])
        self.assertTrue(0.5 < level < 3.0)
        self.assertTrue(0.0 < peak <= 1.0)
        self.assertTrue(all(0.0 <= band < 4.0 for band in bands))

    def test_silence_is_zero(self):
        self.assertEqual(self.capture._features(0.0, 0.0, 60.0, [0.0] * 6), (0.0, 0.0, [0.0] * 6))

    def test_no_stream_is_waiting_not_an_error(self):
        self.capture._set_failure(self.capture._exit_message(1, "cannot find PCM"))
        snapshot = self.capture.snapshot()
        self.assertEqual((snapshot["status"], snapshot["error"]), ("waiting", None))
        self.assertEqual(self.capture._exit_message(1, "x"), WAITING_MESSAGE)

    def test_other_failures_are_still_errors(self):
        self.capture._set_failure("arecord not found")
        self.assertEqual(self.capture.snapshot()["status"], "unavailable")

    def test_a_paused_phone_reads_as_silence(self):
        self.capture._status = "listening"
        self.capture._level = 2.0
        self.capture._history.append((time.monotonic() - 5.0, 3000.0, 0.03))
        snapshot = self.capture.snapshot()
        self.assertEqual((snapshot["status"], snapshot["level"]), ("waiting", 0.0))

    def test_capture_uses_the_bluealsa_device_as_stereo_cd_audio(self):
        command = self.capture._capture_command()
        self.assertEqual(command[command.index("-D") + 1], "bluealsa:PROFILE=a2dp")
        self.assertEqual((command[command.index("-c") + 1], command[command.index("-r") + 1]), ("2", "44100"))

    def test_audio_reaches_the_speakers_even_when_the_lights_do_not_use_it(self):
        self.capture.set_enabled(False)
        self.capture._consume(b"\x00\x01" * 100)
        self.assertEqual(self.sink.chunks, [b"\x00\x01" * 100])
        self.assertEqual(self.capture.take_onsets(), [])

    def test_analysis_downmixes_stereo_to_half_rate_mono(self):
        import struct
        frames = struct.pack("<8h", 100, 300, 200, 400, -100, -300, -200, -400)   # four stereo frames
        mono = self.capture._analysis_samples(frames)
        self.assertEqual(struct.unpack("<2h", mono), (250, -250))

    def test_partial_groups_are_carried_to_the_next_chunk(self):
        import struct
        data = struct.pack("<8h", *([1000] * 8))
        first = self.capture._analysis_samples(data[:6])
        second = self.capture._analysis_samples(data[6:])
        self.assertEqual(first + second, struct.pack("<2h", 1000, 1000))

    def test_analysis_stamps_audio_on_a_steady_clock_despite_bursty_delivery(self):
        import types
        from unittest import mock
        import led.bluetooth_audio as module
        chunk_seconds = 512 / 22050
        clock = types.SimpleNamespace(now=100.0)
        fake_time = types.SimpleNamespace(monotonic=lambda: clock.now)
        self.capture._capture_started()
        stamps = []
        with mock.patch.object(module, "time", fake_time):
            for _ in range(8):                   # bursts of five chunks arriving at the same instant
                clock.now += 5 * chunk_seconds
                stamps.append([self.capture._heard_at(512) for _ in range(5)])
        settled = [stamp for burst in stamps[2:] for stamp in burst]
        gaps = [later - earlier for earlier, later in zip(settled, settled[1:])]
        self.assertTrue(all(abs(gap - chunk_seconds) < 0.001 for gap in gaps), gaps)
        self.assertLessEqual(stamps[-1][-1], clock.now + 1e-9)   # never claims to be from the future

    def test_sink_is_required(self):
        with self.assertRaises(TypeError):
            BluetoothAudioInput("x", object())

    def test_starting_and_stopping_manage_the_sink(self):
        self.capture.start()
        self.assertTrue(self.sink.started)
        self.capture.stop()
        self.assertTrue(self.sink.closed)


class FakePlayer:
    def __init__(self, fail_writes=False):
        self.written = []
        self.fail_writes = fail_writes
        self.stdin = self
        self.closed = False

    def write(self, chunk):
        if self.fail_writes:
            raise BrokenPipeError
        self.written.append(chunk)

    def flush(self):
        pass

    def close(self):
        self.closed = True

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


def wait_for(condition, seconds=2.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


class AplaySinkTests(unittest.TestCase):
    def test_audio_is_played_and_the_player_stops_when_audio_stops(self):
        players = []
        def spawn(command, **kwargs):
            players.append(FakePlayer())
            self.command = command
            return players[-1]
        sink = AplaySink("plughw:CARD=X", spawn=spawn)
        sink.IDLE_SECONDS = 0.1
        sink.start()
        sink.write(b"abcd")
        self.assertTrue(wait_for(lambda: players and players[0].written == [b"abcd"]))
        self.assertEqual(self.command[self.command.index("-D") + 1], "plughw:CARD=X")
        self.assertTrue(wait_for(lambda: players[0].closed))   # idle: the device is released
        sink.close()

    def test_a_failing_player_never_blocks_the_caller(self):
        sink = AplaySink("busy", spawn=lambda command, **kwargs: FakePlayer(fail_writes=True))
        sink.RETRY_SECONDS = 0.05
        sink.start()
        started = time.monotonic()
        for _ in range(500):
            sink.write(b"x" * 4096)
        self.assertLess(time.monotonic() - started, 0.5)
        sink.close()

    def test_a_full_queue_drops_audio_instead_of_waiting(self):
        sink = AplaySink("any")     # not started: nothing drains the queue
        for _ in range(sink.QUEUE_CHUNKS + 20):
            sink.write(b"x")
        self.assertEqual(sink._queue.qsize(), sink.QUEUE_CHUNKS)


class ManagerSourceSwitchTests(unittest.TestCase):
    def setUp(self):
        self.capture = FakeCapture()
        self.manager = ArcadeManager(
            count=60, extra_music_sources=[BluetoothSource(self.capture, 100)])

    def test_microphone_is_the_default_and_both_sources_are_listed(self):
        snapshot = self.manager.music_input_snapshot()
        self.assertEqual(snapshot["selected"], "microphone")
        self.assertEqual([source["name"] for source in snapshot["sources"]], ["microphone", "bluetooth"])

    def test_unknown_source_is_rejected(self):
        with self.assertRaises(ValueError):
            self.manager.set_music_input("tape")
        self.assertEqual(self.manager.music_input, "microphone")

    def test_switching_while_music_plays_moves_the_capture(self):
        self.assertTrue(self.manager.start_music_mode())
        self.manager.set_music_input("bluetooth")
        self.assertTrue(self.capture.enabled)
        self.assertEqual(self.manager.get_state()["audio"]["source"], "bluetooth")
        self.manager.set_music_input("microphone")
        self.assertFalse(self.capture.enabled)

    def test_switching_resets_the_tempo_tracker(self):
        tracker = self.manager._music_beat
        self.manager.set_music_input("bluetooth")
        self.assertIsNot(self.manager._music_beat, tracker)

    def test_stopping_music_releases_every_source(self):
        self.manager.set_music_input("bluetooth")
        self.manager.start_music_mode()
        self.manager.stop_music_mode()
        self.assertFalse(self.capture.enabled)

    def test_bluetooth_delay_is_adjustable(self):
        self.manager.bluetooth_latency_ms = 420
        self.assertEqual(self.manager.music_sources["bluetooth"].delay_ms, 420)

    def test_renders_frames_from_the_bluetooth_source(self):
        from led.frame import Frame
        self.manager.set_music_input("bluetooth")
        self.manager.start_music_mode()
        self.capture.level = 0.6
        frame = Frame(60)
        for _ in range(5):
            self.manager._render_music(frame, 0.02)
            time.sleep(0.03)


class InterfaceTests(unittest.TestCase):
    def test_sources_must_implement_the_interface(self):
        with self.assertRaises(TypeError):
            AudioSource()


if __name__ == "__main__":
    unittest.main()
