"""Live Bluetooth delay tracking: the Pi microphone hears the speakers play the stream.

Bluetooth audio is analyzed just before it goes to the speakers, so its loudness over
time is known. Comparing that with what the Pi microphone hears (the estimator song
auto-sync uses, ``arcade.song.latency``) gives the speaker delay, and the lights'
hold-back follows it while music streams.

The first measurement of a stream searches every plausible delay and jumps straight to
the result; after that, each measurement only looks near the current delay and moves it
a little, so one bad match cannot throw the lights off.
"""

import threading
import time

from arcade.song.latency import BackgroundMeasurement, RecordedLoudness
from led.audio_sources import DelaySync

FIRST_SECONDS = 11.0         # the mic starts with the source; wait for a full window
INTERVAL_SECONDS = 3.0
WINDOW_SECONDS = 10.0        # how much audio each measurement compares
MIC_MARGIN = 0.3             # the newest microphone audio may not have arrived yet
SEARCH_LAGS = (0.0, 1.2)     # first measurement of a stream: anywhere plausible
TRACK_SPAN = 0.18            # afterwards: only this far around the current delay
GAIN = 0.35                  # share of a measured error corrected per measurement
MAX_STEP = 0.03
MAX_DELAY = 1.5              # the admin slider's range
SAVE_CHANGE_MS = 3
SAVE_INTERVAL = 60.0         # write a learned delay to disk at most this often


class BluetoothDelaySync(DelaySync):
    """``DelaySync`` for ``BluetoothSource``: ``stream`` is the Bluetooth capture and
    ``mic`` the Pi microphone (both keep ``history_since``). ``on_learned(ms)`` persists
    a settled delay; it runs on a background thread."""

    def __init__(self, stream, mic, enabled=True, on_learned=None,
                 clock=time.monotonic, measure=BackgroundMeasurement):
        self.stream, self.mic = stream, mic
        self.enabled = bool(enabled)
        self.on_learned = on_learned
        self._clock, self._measure = clock, measure
        self._running = False
        self._mic_on = False
        self.state, self.score = "off", None
        self._saved_ms, self._saved_at = None, None
        self._learned = None             # the last delay a measurement confirmed
        self._new_stream()

    # -- DelaySync -----------------------------------------------------------------
    def start(self):
        self._running = True
        self._new_stream()
        self._follow_setting()

    def stop(self):
        self._running = False
        self._follow_setting()
        self._measurement = None
        if self._learned is not None:
            self._save(self._learned, force=True)

    def update(self, delay_ms):
        self._follow_setting()
        if not self._mic_on:
            return delay_ms
        delay = delay_ms / 1000.0
        if self._measurement is not None:
            result = self._measurement.result
            if result is None:
                return delay_ms
            self._measurement = None
            delay = self._apply(result, delay)
        now = self._clock()
        if self.stream.snapshot()["status"] != "listening":
            self._new_stream()          # paused or a different phone: search afresh
            self.state = "waiting"
            return delay * 1000.0
        if self._streaming_since is None:
            self._streaming_since, self._next = now, now + FIRST_SECONDS
            self.state = "listening"
        if now >= self._next:
            self._next = now + INTERVAL_SECONDS
            self._start_measurement(now, delay)
        return delay * 1000.0

    def describe(self):
        if not self.enabled or self.mic is None:
            return {"enabled": False, "state": "off", "score": None}
        state = self.state
        if self._mic_on and self.mic.snapshot()["status"] == "unavailable":
            state = "no microphone"
        return {"enabled": True, "state": state, "score": self.score}

    # -- measuring -----------------------------------------------------------------
    def _new_stream(self):
        self._streaming_since = self._next = None
        self._measurement = None
        self._acquired = False

    def _follow_setting(self):
        """The Pi microphone listens only while this source plays with sync on."""
        wanted = self._running and self.enabled and self.mic is not None
        if wanted != self._mic_on:
            self.mic.set_enabled(wanted)
            self._mic_on = wanted
        if not wanted:
            self.state = "off"

    def _start_measurement(self, now, delay):
        if self._acquired:
            lags = (max(0.0, delay - TRACK_SPAN), min(MAX_DELAY, delay + TRACK_SPAN))
        else:
            lags = SEARCH_LAGS
        end = now - MIC_MARGIN
        origin = end - WINDOW_SECONDS - lags[1] - 1.0
        reference = RecordedLoudness(self.stream.history_since(origin - 0.5), origin)
        window = (end - WINDOW_SECONDS - origin, end - origin)
        self._measurement = self._measure(self.mic.history_since(origin), origin, reference, window, lags)

    def _apply(self, result, delay):
        self.score = result.get("score")
        if not result.get("ok"):
            self.state = "weak"         # quiet passage or room noise: leave the delay alone
            return delay
        measured = result["latency_ms"] / 1000.0
        if self._acquired:
            delay += max(-MAX_STEP, min(MAX_STEP, (measured - delay) * GAIN))
        else:
            delay, self._acquired = measured, True
        delay = max(0.0, min(MAX_DELAY, delay))
        self.state = "locked" if abs(measured - delay) < 0.02 else "adjusting"
        if self.state == "locked":
            self._learned = delay
            self._save(delay)
        return delay

    def _save(self, delay, force=False):
        milliseconds = int(round(delay * 1000.0))
        now = self._clock()
        if self.on_learned is None or (self._saved_ms is not None and (
                abs(milliseconds - self._saved_ms) < SAVE_CHANGE_MS
                or (not force and now - self._saved_at < SAVE_INTERVAL))):
            return
        self._saved_ms, self._saved_at = milliseconds, now
        threading.Thread(target=self.on_learned, args=(milliseconds,),
                         name="bluetooth-delay-save", daemon=True).start()
