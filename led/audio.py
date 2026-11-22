"""Optional microphone capture for the free music visualizer.

Audio is read from ALSA's ``arecord`` command so no Python audio package is
needed. The worker computes level, clap, and coarse frequency-band features;
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

log = logging.getLogger("led.audio")


class AudioInput:
    SAMPLE_RATE = 16000
    CHUNK_BYTES = 1024
    BAND_CENTERS_HZ = (80, 180, 360, 900, 2400, 6000)
    # Small ALSA periods keep chunk timestamps within ~20 ms of when sound arrived,
    # which the speaker-to-microphone latency measurement depends on.
    LOW_LATENCY_ARGS = ("-F", "20000", "-B", "80000")
    HISTORY_SECONDS = 60

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

    def history_since(self, start_time):
        """Loudness chunks that arrived after ``start_time`` (time.monotonic)."""
        with self._lock:
            return [chunk for chunk in self._history if chunk[0] >= start_time]

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
                self._stopping.wait(2.0)
                continue

            process = None
            started = time.monotonic()
            try:
                process = subprocess.Popen(
                    [
                        "arecord", "-q", "-D", self.device,
                        "-t", "raw", "-f", "S16_LE", "-c", "1",
                        "-r", str(self.SAMPLE_RATE),
                        *(self.LOW_LATENCY_ARGS if self._low_latency else ()),
                    ],
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
                    detail = error_output or "no ALSA error details were reported"
                    self._set_failure(
                        f"arecord exited with status {return_code}: {detail} "
                        "Check the microphone and LED_AUDIO_DEVICE."
                    )
                    self._stopping.wait(2.0)
            except Exception as exc:
                if process and process.poll() is None:
                    process.terminate()
                self._process = None
                self._set_failure(f"microphone capture failed: {exc}")
                log.exception("Microphone capture failed")
                self._stopping.wait(2.0)

        self._process = None

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
            dynamic_range = max(600.0, floor * 5.0)
            self._level = max(0.0, min(1.0, (rms - floor) / dynamic_range))
            self._peak = max(0.0, min(1.0, (peak - floor) / (floor * 10.0 + 900.0)))
            band_noise = floor / 32768.0 * 2.0
            band_range = max(0.025, floor / 32768.0 * 8.0)
            self._bands = [
                max(0.0, min(1.0, (magnitude - band_noise) / band_range)) ** 0.75
                for magnitude in self._frequency_band_amplitudes(samples)
            ]
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

    def _frequency_band_amplitudes(self, samples):
        """Estimate six coarse frequency bands with stdlib Goertzel bins."""
        if not samples:
            return [0.0] * len(self.BAND_CENTERS_HZ)
        normalized = [sample / 32768.0 for sample in samples]
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
