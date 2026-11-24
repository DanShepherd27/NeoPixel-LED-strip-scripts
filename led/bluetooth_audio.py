"""The Bluetooth stream a phone sends to the Pi, analyzed for the sound-reactive lights.

BlueALSA exposes the received A2DP audio as an ALSA capture device, so it is read with
the same ``arecord`` pipeline and analysis as the microphone. Only the calibration
differs: digital audio is far louder than a room microphone and has no noise floor.
"""

import time

from led.audio import AudioInput

WAITING_MESSAGE = "Waiting for a phone to stream Bluetooth audio."


class BluetoothAudioInput(AudioInput):
    # The BlueALSA PCM does not take the small ALSA periods the microphone path asks for.
    LOW_LATENCY_ARGS = ()
    RETRY_SECONDS = 1.0     # how soon to look for a phone that has started playing
    STALE_SECONDS = 0.5     # no audio for this long means the phone paused or left
    # Full-scale music sits near RMS 3000-10000; bands are sine amplitudes where 1.0 is full scale.
    LEVEL_RANGE = 4000.0
    PEAK_RANGE = 24000.0
    BAND_RANGE = 0.12

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
