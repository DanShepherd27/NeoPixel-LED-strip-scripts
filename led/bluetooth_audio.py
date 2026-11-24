"""The Bluetooth stream a phone sends to the Pi: played on the speakers and analyzed for the lights.

BlueALSA lets only one program read the phone's stream, so this input is the one reader.
It forwards the audio to a ``PcmSink`` (the speakers) at all times, and runs the same
analysis as the microphone (level, six bands, kick/snare onsets) while the sound-reactive
lights use it. Only the calibration differs: digital audio is far louder than a room
microphone and has no noise floor.
"""

import array
import struct
import sys
import time

from led.audio import AudioInput, numpy
from led.pcm_sink import PcmSink

WAITING_MESSAGE = "Waiting for a phone to stream Bluetooth audio."


class BluetoothAudioInput(AudioInput):
    CAPTURE_RATE = 44100
    CAPTURE_CHANNELS = 2
    # Analysis runs on a mono signal at half the capture rate (four samples averaged per output).
    SAMPLE_RATE = 22050
    FFT_SIZE = 1536            # about the same window length as the microphone's
    CHUNK_BYTES = 4096         # 1024 stereo frames, 23 ms
    LOW_LATENCY_ARGS = ()
    RETRY_SECONDS = 1.0        # how soon to look for a phone that has started playing
    STALE_SECONDS = 0.5        # no analyzed audio for this long means the phone paused or left
    # Full-scale music sits near RMS 3000-10000; bands are sine amplitudes where 1.0 is full scale.
    LEVEL_RANGE = 4000.0
    PEAK_RANGE = 24000.0
    BAND_RANGE = 0.12
    DRIFT_FOLLOW = 0.001       # how fast the stream clock follows a slowly drifting source

    def __init__(self, device, sink):
        super().__init__(device)
        if not isinstance(sink, PcmSink):
            raise TypeError("sink must be a PcmSink")
        self._sink = sink
        self._low_latency = False
        self._carry = b""
        self._origin = None
        self._stream_samples = 0

    # -- lifecycle ---------------------------------------------------------------------
    def start(self):
        self._sink.start()
        super().start()

    def stop(self):
        super().stop()
        self._sink.close()

    def set_enabled(self, enabled):
        """Switch the analysis. The phone's audio keeps reaching the speakers either way."""
        if enabled:
            self._origin = None
            self._stream_samples = 0
            self._enabled.set()
            return
        self._enabled.clear()
        with self._lock:
            self._level = 0.0
            self._peak = 0.0
            self._bands = [0.0] * len(self.BAND_CENTERS_HZ)
            self._rms = 0.0
            self._clap_until = 0.0
        self._origin = None

    def _wants_capture(self):
        return True

    def _capture_started(self):
        self._carry = b""
        self._origin = None
        self._stream_samples = 0

    def _capture_command(self):
        return [
            "arecord", "-q", "-D", self.device, "-t", "raw", "-f", "S16_LE",
            "-c", str(self.CAPTURE_CHANNELS), "-r", str(self.CAPTURE_RATE),
        ]

    # -- audio -------------------------------------------------------------------------
    def _consume(self, chunk):
        self._sink.write(chunk)   # the speakers come first; analysis must never delay them
        if not self._enabled.is_set():
            return
        mono = self._analysis_samples(chunk)
        if mono:
            self._analyze(mono, now=self._heard_at(len(mono) // 2))

    def _analysis_samples(self, raw):
        """Mono S16 bytes at the analysis rate from stereo capture bytes."""
        data = self._carry + raw
        usable = len(data) - len(data) % 8     # four 16-bit values make one output sample
        self._carry = data[usable:]
        if not usable:
            return b""
        if numpy is not None:
            values = numpy.frombuffer(data[:usable], dtype="<i2").astype(numpy.int32)
            return (values.reshape(-1, 4).sum(axis=1) // 4).astype("<i2").tobytes()
        values = array.array("h")
        values.frombytes(data[:usable])
        if sys.byteorder == "big":
            values.byteswap()
        means = [(values[i] + values[i + 1] + values[i + 2] + values[i + 3]) // 4
                 for i in range(0, len(values), 4)]
        return struct.pack(f"<{len(means)}h", *means)

    def _heard_at(self, samples):
        """When the end of this chunk plays, on a steady clock.

        ``arecord`` hands over audio in bursts, so arrival times jitter by a period.
        The speakers play the stream at a constant rate, so each sample is stamped
        origin + position: the origin is the earliest arrival-based estimate, and it
        follows a slowly drifting source only upward.
        """
        arrival = time.monotonic()
        self._stream_samples += samples
        candidate = arrival - self._stream_samples / self.SAMPLE_RATE
        if self._origin is None or candidate < self._origin:
            self._origin = candidate
        else:
            self._origin += (candidate - self._origin) * self.DRIFT_FOLLOW
        return self._origin + self._stream_samples / self.SAMPLE_RATE

    # -- status ------------------------------------------------------------------------
    def snapshot(self):
        snapshot = super().snapshot()
        with self._lock:
            last_chunk = self._history[-1][0] if self._history else 0.0
        if snapshot["status"] == "listening" and time.monotonic() - last_chunk > self.STALE_SECONDS:
            snapshot.update(status="waiting", level=0.0, peak=0.0,
                            bands=[0.0] * len(self.BAND_CENTERS_HZ), clap=False)
        return snapshot

    def _exit_message(self, return_code, error_output):
        # No stream is the normal state before a phone plays, not an error to report.
        return WAITING_MESSAGE

    def _set_failure(self, message):
        if message != WAITING_MESSAGE:
            super()._set_failure(message)
            return
        with self._lock:
            self._status = "waiting"
            self._error = None
            self._level = 0.0
            self._peak = 0.0
            self._bands = [0.0] * len(self.BAND_CENTERS_HZ)

    def _features(self, rms, peak, floor, amplitudes):
        level = max(0.0, min(4.0, rms / self.LEVEL_RANGE))
        peak = max(0.0, min(1.0, peak / self.PEAK_RANGE))
        bands = [max(0.0, min(4.0, magnitude / self.BAND_RANGE)) ** 0.75 for magnitude in amplitudes]
        return level, peak, bands
