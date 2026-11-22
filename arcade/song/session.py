"""One run of the song show: playback clock, Pi audio, sync, and choreography."""

import time

from arcade.song.analysis import SONG_AUDIO, SongAnalysis
from arcade.song.choreography import SongChoreography
from arcade.song.latency import BackgroundMeasurement
from arcade.song.player import PiAudioPlayer
from arcade.song.timeline import section_at

END_PADDING_SECONDS = 1.0
CALIBRATION_SECONDS = 18.0
CALIBRATION_WINDOW = (1.0, 17.5)
CALIBRATION_LAGS = (0.0, 1.0)
SYNC_FIRST_SECONDS = 12.0   # let the music get going before trusting the mic
SYNC_INTERVAL_SECONDS = 3.0
SYNC_WINDOW_SECONDS = 10.0
SYNC_LAG_SPAN = 0.18        # auto-sync only looks this far around the current latency
SYNC_GAIN = 0.35            # fraction of a measured error corrected per measurement
SYNC_MAX_STEP = 0.03
SYNC_MAX_DRIFT = 0.30       # never wander further than this from the starting latency


class SongSession:
    def __init__(self, count, pi_audio, audio_latency_ms=250, audio_device=None,
                 analysis=None, mic=None, auto_sync=True, calibrate=False):
        self.pi_audio = pi_audio
        self.analysis = analysis or SongAnalysis()
        self.choreography = SongChoreography(count, self.analysis)
        self.duration = self.choreography.duration
        self.audio_latency = audio_latency_ms / 1000.0
        self._initial_latency = self.audio_latency
        self.pi_audio_error = None
        self.calibrating = calibrate
        self.calibration_result = None
        self.sync_enabled = bool(pi_audio and mic and (auto_sync or calibrate))
        self.sync_state = "off"
        self.sync_score = None
        self._mic = mic if self.sync_enabled else None
        if self._mic is not None:
            self._mic.set_enabled(True)
        self._measurement = None
        self._next_sync = SYNC_FIRST_SECONDS
        self._player = PiAudioPlayer(SONG_AUDIO, audio_device)
        if pi_audio:
            self.pi_audio_error = self._player.start()
        self._started = time.monotonic()  # the clock "latency" is measured from

    @property
    def elapsed(self):
        return time.monotonic() - self._started

    @property
    def position(self):
        """Seconds of the song being heard, allowing for audio start-up delay."""
        return max(0.0, self.elapsed - (self.audio_latency if self.pi_audio else 0.0))

    @property
    def latency_ms(self):
        return round(self.audio_latency * 1000.0, 1)

    @property
    def finished(self):
        if self.calibrating:
            return self.calibration_result is not None
        return self.position >= self.duration + END_PADDING_SECONDS

    def update(self):
        """Per-frame housekeeping: drive calibration and live latency tracking."""
        if self.calibrating:
            self._update_calibration()
        elif self._mic is not None:
            self._update_auto_sync()

    def render(self, frame, dt):
        self.choreography.render(frame, self.position, dt)

    def stop(self):
        self._player.stop()
        if self._mic is not None:
            self._mic.set_enabled(False)

    # -- latency measurement -------------------------------------------------
    def _start_measurement(self, window, lags):
        history = self._mic.history_since(self._started + window[0] - 1.0)
        self._measurement = BackgroundMeasurement(
            history, self._started, self.analysis, window, lags,
        )

    def _update_calibration(self):
        problem = self.pi_audio_error or self._player.failure()
        if problem or not self.pi_audio or self._mic is None:
            self.calibration_result = {
                "ok": False, "message": problem or "No microphone is available.",
            }
            return
        if self._measurement is None and self.elapsed >= CALIBRATION_SECONDS:
            self._start_measurement(CALIBRATION_WINDOW, CALIBRATION_LAGS)
        if self._measurement is not None and self._measurement.result is not None:
            self.calibration_result = self._measurement.result

    def _update_auto_sync(self):
        if self._measurement is not None:
            result = self._measurement.result
            if result is None:
                return
            self._measurement = None
            self._apply_sync(result)
        if self.elapsed >= self._next_sync and self.pi_audio_error is None:
            self._next_sync = self.elapsed + SYNC_INTERVAL_SECONDS
            end = self.elapsed - 0.3
            low = max(0.0, self.audio_latency - SYNC_LAG_SPAN)
            self._start_measurement(
                (end - SYNC_WINDOW_SECONDS, end), (low, self.audio_latency + SYNC_LAG_SPAN),
            )

    def _apply_sync(self, result):
        self.sync_score = result.get("score")
        if not result["ok"]:
            self.sync_state = "weak"  # quiet passage, noise or no mic: leave latency alone
            return
        error = result["latency_ms"] / 1000.0 - self.audio_latency
        step = max(-SYNC_MAX_STEP, min(SYNC_MAX_STEP, error * SYNC_GAIN))
        proposed = self.audio_latency + step
        low = self._initial_latency - SYNC_MAX_DRIFT
        self.audio_latency = max(0.0, low, min(self._initial_latency + SYNC_MAX_DRIFT, proposed))
        self.sync_state = "locked" if abs(error) < 0.02 else "adjusting"

    def snapshot(self):
        index, section, _, _ = section_at(self.position)
        mic_error = None
        if self.sync_enabled and self._mic is not None:
            mic_state = self._mic.snapshot()
            mic_error = mic_state["error"] if mic_state["status"] == "unavailable" else None
        return {
            "position": round(min(self.position, self.duration), 2),
            "duration": round(self.duration, 2),
            "section": section.name,
            "section_index": index,
            "pi_audio": self.pi_audio,
            "pi_audio_error": self.pi_audio_error or self._player.failure(),
            "calibrating": self.calibrating,
            "calibration_progress": round(min(1.0, self.elapsed / CALIBRATION_SECONDS), 2),
            "latency_ms": self.latency_ms,
            "sync": {
                "enabled": self.sync_enabled and not self.calibrating,
                "state": "no microphone" if mic_error else self.sync_state,
                "score": self.sync_score,
            },
        }
