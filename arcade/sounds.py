"""Retro arcade sound effects played on the Pi's speaker.

Sounds are short square-wave melodies synthesized with the standard library
into WAV files at start-up and played with ``aplay`` (ALSA). Playback never
blocks the renderer: each sound is a detached process, and sounds are dropped
when several are already playing. Without ``aplay`` everything is silent.
"""

import logging
import math
import os
import shutil
import struct
import subprocess
import tempfile
import wave

log = logging.getLogger("arcade.sounds")

SAMPLE_RATE = 22050
VOLUME = 0.3
MAX_OVERLAPPING = 3

# Each sound is a list of (frequency Hz, milliseconds); 0 Hz is a rest.
SOUNDS = {
    "beep": [(660, 90)],
    "go": [(1320, 260)],
    "serve": [(330, 70)],
    "point": [(440, 90), (330, 90), (220, 220)],
    "level_clear": [(523, 90), (659, 90), (784, 90), (1047, 260)],
    "level_start": [(392, 80), (523, 80), (659, 80), (784, 160)],
    "win": [(523, 110), (523, 110), (523, 110), (659, 200), (784, 380)],
    "fire": [(1500, 25), (1000, 25), (600, 45)],
    "oops": [(220, 110), (160, 180)],
}
# A hit's pitch rises with the ball speed, so faster play is audible.
for _step in range(8):
    SOUNDS["hit%d" % _step] = [(520 + 70 * _step, 55)]


def synthesize(notes):
    """Return 16-bit mono PCM bytes for a list of (frequency, milliseconds) notes."""
    samples = []
    for frequency, milliseconds in notes:
        count = int(SAMPLE_RATE * milliseconds / 1000.0)
        for index in range(count):
            fade = min(1.0, (count - index) / (SAMPLE_RATE * 0.02))
            wave_value = 0.0 if frequency <= 0 else (
                1.0 if math.sin(2.0 * math.pi * frequency * index / SAMPLE_RATE) >= 0 else -1.0)
            samples.append(int(32767 * VOLUME * fade * wave_value))
    return struct.pack("<%dh" % len(samples), *samples)


class SoundPlayer:
    def __init__(self, device="default", enabled=True):
        self.device = device
        self._playing = []
        self._directory = None
        self._aplay = shutil.which("aplay") if enabled else None
        if enabled and self._aplay is None:
            log.info("aplay not found; game sounds are disabled")
        if self._aplay:
            self._directory = tempfile.mkdtemp(prefix="led-arcade-sounds-")
            for name, notes in SOUNDS.items():
                with wave.open(self._path(name), "wb") as output:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(SAMPLE_RATE)
                    output.writeframes(synthesize(notes))

    def _path(self, name):
        return os.path.join(self._directory, name + ".wav")

    def play(self, name):
        if not self._aplay or name not in SOUNDS:
            return
        self._playing = [process for process in self._playing if process.poll() is None]
        if len(self._playing) >= MAX_OVERLAPPING:
            return
        try:
            self._playing.append(subprocess.Popen(
                [self._aplay, "-q", "-D", self.device, self._path(name)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ))
        except OSError as exc:
            log.warning("Could not play %s: %s", name, exc)
            self._aplay = None
