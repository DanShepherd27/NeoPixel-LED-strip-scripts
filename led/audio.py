"""Optional microphone capture for the free music visualizer.

Audio is read from ALSA's ``arecord`` command so no Python audio package is
needed. The worker computes level, clap, coarse frequency bands and kick/snare
onset strengths (with numpy when installed, stdlib Goertzel bins otherwise);
the central LED renderer remains the sole writer to the strip.
"""

import collections
import logging
import math
import shutil
import struct
import subprocess
import threading
import time

try:
    import numpy
except ImportError:  # the visualizer still works, with coarser bands
    numpy = None

log = logging.getLogger("led.audio")

# Same ranges the browser microphone reports.
BAND_RANGES_HZ = ((40, 150), (150, 300), (300, 600), (600, 1500), (1500, 4000), (4000, 8000))
KICK_RANGE_HZ = (30, 150)
SNARE_RANGE_HZ = (1500, 7000)
# Fallback Goertzel probes spread across each onset range.
KICK_PROBES_HZ = (40, 55, 70, 90, 115, 140)
SNARE_PROBES_HZ = (1600, 2200, 3000, 4000, 5200, 6500)


class AudioInput:
    SAMPLE_RATE = 16000
    CHUNK_BYTES = 1024
    BAND_CENTERS_HZ = (80, 180, 360, 900, 2400, 6000)
    # Small ALSA periods keep chunk timestamps within ~20 ms of when sound arrived,
    # which the speaker-to-microphone latency measurement depends on.
    LOW_LATENCY_ARGS = ("-F", "20000", "-B", "80000")
    HISTORY_SECONDS = 60
    FFT_SIZE = 1024
    RETRY_SECONDS = 2.0

    def __init__(self, device="default"):
        self.device = device or "default"
        self._enabled = threading.Event()
        self._stopping = threading.Event()
        self._lock = threading.Lock()
        self._process = None
        self._thread = None
        self._status = "off"
        self._error = None
        self._level = 0.0
        self._peak = 0.0
        self._bands = [0.0] * len(self.BAND_CENTERS_HZ)
        self._rms = 0.0
        self._noise_floor = None
        self._clap_until = 0.0
        self._last_clap = 0.0
        self._low_latency = True
        # (monotonic arrival time, rms, seconds covered) per captured chunk.
        self._history = collections.deque(maxlen=self.HISTORY_SECONDS * 100)
        self._onsets = collections.deque(maxlen=64)
        self._onset = OnsetMeter()
        self._window = []

    def history_since(self, start_time):
        """Loudness chunks that arrived after ``start_time`` (time.monotonic)."""
        with self._lock:
            return [chunk for chunk in self._history if chunk[0] >= start_time]

    def take_onsets(self):
        """Kick/snare onset samples since the last call, as ``(monotonic time
        the sound happened, "kick" or "snare", strength 0-1)``."""
        with self._lock:
            samples = list(self._onsets)
            self._onsets.clear()
            return samples

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stopping.clear()
        self._thread = threading.Thread(
            target=self._run, name="microphone-capture", daemon=True,
        )
        self._thread.start()

    def set_enabled(self, enabled):
        if enabled:
            self._enabled.set()
            with self._lock:
                if self._status in ("off", "unavailable"):
                    self._status = "starting"
                self._error = None
        else:
            self._enabled.clear()
            with self._lock:
                self._status = "off"
                self._level = 0.0
                self._peak = 0.0
                self._bands = [0.0] * len(self.BAND_CENTERS_HZ)
                self._rms = 0.0
                self._clap_until = 0.0
            # A capture waiting for data (a paused phone) would otherwise stay open.
            process = self._process
            if process and process.poll() is None:
                process.terminate()

    def stop(self):
        self._enabled.clear()
        self._stopping.set()
        process = self._process
        if process and process.poll() is None:
            process.terminate()
        if self._thread:
            self._thread.join(timeout=2.0)

    def snapshot(self):
        with self._lock:
            return {
                "status": self._status,
                "error": self._error,
                "device": self.device,
                "level": round(self._level, 3),
                "peak": round(self._peak, 3),
                "bands": list(self._bands),
                "latency_ms": round(
                    (self.CHUNK_BYTES / 2) / self.SAMPLE_RATE * 500.0, 1,
                ),
                "noise_floor": round(self._noise_floor or 0.0, 1),
                "clap": time.monotonic() < self._clap_until,
            }

    def _run(self):
        while not self._stopping.is_set():
            if not self._enabled.wait(timeout=0.2):
                continue
            if not shutil.which("arecord"):
                self._set_failure("arecord not found; install alsa-utils on the Pi")
                self._stopping.wait(self.RETRY_SECONDS)
                continue

            process = None
            started = time.monotonic()
            try:
                process = subprocess.Popen(
                    self._capture_command(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                )
                self._process = process
                with self._lock:
                    self._status = "listening"
                    self._error = None
                log.info("Microphone capture started (ALSA device=%s)", self.device)

                while self._enabled.is_set() and not self._stopping.is_set():
                    chunk = process.stdout.read(self.CHUNK_BYTES)
                    if not chunk:
                        break
                    self._analyze(chunk[:len(chunk) & ~1])

                if process.poll() is None:
                    process.terminate()
                return_code = process.wait(timeout=1.0)
                error_output = process.stderr.read().decode("utf-8", errors="replace").strip()
                self._process = None
                if (self._low_latency and self._enabled.is_set() and
                        time.monotonic() - started < 3.0):
                    # The device rejected the small buffer; use ALSA defaults.
                    log.warning("arecord failed with low-latency buffers (%s); retrying with defaults",
                                error_output or return_code)
                    self._low_latency = False
                    continue
                if self._enabled.is_set() and not self._stopping.is_set():
                    self._set_failure(self._exit_message(return_code, error_output))
                    self._stopping.wait(self.RETRY_SECONDS)
            except Exception as exc:
                if process and process.poll() is None:
                    process.terminate()
                self._process = None
                self._set_failure(f"microphone capture failed: {exc}")
                log.exception("Microphone capture failed")
                self._stopping.wait(self.RETRY_SECONDS)

        self._process = None

    def _capture_command(self):
        """The ``arecord`` command that streams this source as mono 16-bit PCM."""
        return [
            "arecord", "-q", "-D", self.device,
            "-t", "raw", "-f", "S16_LE", "-c", "1",
            "-r", str(self.SAMPLE_RATE),
            *(self.LOW_LATENCY_ARGS if self._low_latency else ()),
        ]

    def _exit_message(self, return_code, error_output):
        detail = error_output or "no ALSA error details were reported"
        return (f"arecord exited with status {return_code}: {detail} "
                "Check the microphone and LED_AUDIO_DEVICE.")

    def _set_failure(self, message):
        with self._lock:
            should_log = self._status != "unavailable" or self._error != message
            self._status = "unavailable"
            self._error = message
            self._level = 0.0
            self._peak = 0.0
            self._bands = [0.0] * len(self.BAND_CENTERS_HZ)
        if should_log:
            log.error("%s", message)

    def _analyze(self, chunk):
        samples = [sample[0] for sample in struct.iter_unpack("<h", chunk)]
        if not samples:
            return
        squares = sum(sample * sample for sample in samples)
        rms = math.sqrt(squares / len(samples))
        peak = max(abs(sample) for sample in samples)
        now = time.monotonic()

        with self._lock:
            if self._noise_floor is None:
                self._noise_floor = min(500.0, max(60.0, rms))
            elif rms < self._noise_floor:
                self._noise_floor += (rms - self._noise_floor) * 0.08
            elif rms < self._noise_floor * 2.0:
                self._noise_floor += (rms - self._noise_floor) * 0.004

            floor = self._noise_floor
            amplitudes, kick_spectrum, snare_spectrum = self._spectrum(samples)
            self._level, self._peak, self._bands = self._features(rms, peak, floor, amplitudes)
            sound_time = now - len(samples) / self.SAMPLE_RATE
            for name, strength in self._onset.measure(now, kick_spectrum, snare_spectrum):
                self._onsets.append((sound_time, name, strength))
            self._rms = rms
            self._history.append((now, rms, len(samples) / self.SAMPLE_RATE))

            is_clap = (
                rms > max(120.0, floor * 1.35)
                and peak > max(1800.0, floor * 5.0)
                and peak / max(1.0, rms) > 3.0
                and now - self._last_clap > 0.16
            )
            if is_clap:
                self._last_clap = now
                self._clap_until = now + 0.18

    def _features(self, rms, peak, floor, amplitudes):
        """Normalized ``(level, peak, bands)``, calibrated for a room microphone.

        Level and bands may exceed 1 for loud music; the renderer auto-gain scales them.
        """
        dynamic_range = max(600.0, floor * 5.0)
        level = max(0.0, min(4.0, (rms - floor) / dynamic_range))
        peak = max(0.0, min(1.0, (peak - floor) / (floor * 10.0 + 900.0)))
        band_noise = floor / 32768.0 * 2.0
        band_range = max(0.025, floor / 32768.0 * 8.0)
        bands = [
            max(0.0, min(4.0, (magnitude - band_noise) / band_range)) ** 0.75
            for magnitude in amplitudes
        ]
        return level, peak, bands

    def _spectrum(self, samples):
        """Band amplitudes plus the kick and snare range spectra for onsets."""
        normalized = [sample / 32768.0 for sample in samples]
        if numpy is None:
            return (
                self._frequency_band_amplitudes(normalized),
                [self._goertzel_amplitude(normalized, f) for f in KICK_PROBES_HZ],
                [self._goertzel_amplitude(normalized, f) for f in SNARE_PROBES_HZ],
            )
        # A sliding window twice the chunk length gives 15.6 Hz bins, enough to
        # separate the kick from the bass line.
        self._window = (self._window + normalized)[-self.FFT_SIZE:]
        window = numpy.zeros(self.FFT_SIZE)
        window[-len(self._window):] = self._window
        spectrum = numpy.abs(numpy.fft.rfft(window * numpy.hanning(self.FFT_SIZE)))
        spectrum *= 4.0 / self.FFT_SIZE   # sine amplitude, like the Goertzel bins
        freqs = numpy.fft.rfftfreq(self.FFT_SIZE, 1.0 / self.SAMPLE_RATE)

        def bins(low, high):
            return spectrum[(freqs >= low) & (freqs < high)]

        amplitudes = []
        for low, high in BAND_RANGES_HZ:
            values = numpy.sort(bins(low, high))[::-1]
            loudest = values[:max(1, int(math.ceil(len(values) * 0.35)))]
            amplitudes.append(float(numpy.sqrt(numpy.mean(loudest ** 2))))
        return amplitudes, bins(*KICK_RANGE_HZ).tolist(), bins(*SNARE_RANGE_HZ).tolist()

    def _frequency_band_amplitudes(self, normalized):
        """Estimate six coarse frequency bands with stdlib Goertzel bins."""
        amplitudes = []
        for center in self.BAND_CENTERS_HZ:
            nearby = (center * 0.85, center, center * 1.15)
            amplitudes.append(max(
                self._goertzel_amplitude(normalized, frequency)
                for frequency in nearby
            ))
        return amplitudes

    def _goertzel_amplitude(self, samples, frequency):
        omega = 2.0 * math.pi * frequency / self.SAMPLE_RATE
        coefficient = 2.0 * math.cos(omega)
        previous = previous_two = 0.0
        for sample in samples:
            current = sample + coefficient * previous - previous_two
            previous_two, previous = previous, current
        power = max(
            0.0,
            previous * previous + previous_two * previous_two
            - coefficient * previous * previous_two,
        )
        return 2.0 * math.sqrt(power) / max(1, len(samples))


class OnsetMeter:
    """Kick and snare onset strength from consecutive spectra: the positive change
    of the log-compressed magnitudes (spectral flux, as in the song analyzer),
    scaled 0-1 against a slowly decaying recent maximum."""

    CEILING_DECAY_PER_SECOND = 0.25
    MIN_CEILING = 0.3    # about the flux of a soft real kick; room noise stays below

    def __init__(self):
        self._previous = {}
        self._ceiling = {"kick": self.MIN_CEILING, "snare": self.MIN_CEILING}
        self._last_time = None

    def measure(self, now, kick_spectrum, snare_spectrum):
        decay = 1.0
        if self._last_time is not None:
            decay = math.exp(-(now - self._last_time) * self.CEILING_DECAY_PER_SECOND)
        self._last_time = now
        results = []
        for name, spectrum in (("kick", kick_spectrum), ("snare", snare_spectrum)):
            compressed = [math.log1p(1000.0 * value) for value in spectrum]
            previous = self._previous.get(name)
            self._previous[name] = compressed
            if previous is None or len(previous) != len(compressed) or not compressed:
                continue
            flux = sum(max(0.0, now_value - before)
                       for now_value, before in zip(compressed, previous)) / len(compressed)
            ceiling = max(self.MIN_CEILING, self._ceiling[name] * decay, flux)
            self._ceiling[name] = ceiling
            strength = min(1.0, flux / ceiling)
            if strength > 0.0:
                results.append((name, strength))
        return results
