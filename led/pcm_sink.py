"""Where raw PCM audio goes to be heard.

The Bluetooth input reads a phone's stream once, because BlueALSA lets only one program
open it, and hands the audio to a ``PcmSink`` for the speakers while it analyzes it for
the lights. Another destination (a file, a network speaker) is another subclass.
"""

import abc
import logging
import queue
import subprocess
import threading
import time

log = logging.getLogger("led.pcm_sink")


class PcmSink(abc.ABC):
    @abc.abstractmethod
    def start(self):
        """Get ready to accept audio."""

    @abc.abstractmethod
    def write(self, chunk):
        """Take one chunk of PCM. Must never block the caller; drop audio instead."""

    @abc.abstractmethod
    def close(self):
        """Stop and release the output."""


class AplaySink(PcmSink):
    """Plays raw 16-bit stereo PCM through ``aplay``.

    The player runs only while audio arrives: ALSA's ``plughw`` devices are exclusive,
    so keeping one open all the time would lock out the game sounds and the song show.
    """

    QUEUE_CHUNKS = 64        # about 1.5 s of audio at the default chunk size
    IDLE_SECONDS = 1.5       # no audio for this long closes the player
    RETRY_SECONDS = 1.0      # wait before trying a device that was busy or failed

    def __init__(self, device, rate=44100, channels=2, buffer_us=200000, spawn=subprocess.Popen):
        self.device = device
        self._command = [
            "aplay", "-q", "-D", device, "-t", "raw", "-f", "S16_LE",
            "-c", str(channels), "-r", str(rate), "-B", str(buffer_us),
        ]
        self._spawn = spawn
        self._queue = queue.Queue(maxsize=self.QUEUE_CHUNKS)
        self._stopping = threading.Event()
        self._thread = None
        self._player = None
        self._last_audio = 0.0
        self._retry_at = 0.0
        self._warned = False

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name="bluetooth-playback", daemon=True)
        self._thread.start()

    def write(self, chunk):
        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            pass   # the speakers are behind; lose this audio rather than stall the capture

    def close(self):
        self._stopping.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._stop_player()

    def _run(self):
        while not self._stopping.is_set():
            try:
                chunk = self._queue.get(timeout=0.25)
            except queue.Empty:
                if self._player is not None and time.monotonic() - self._last_audio > self.IDLE_SECONDS:
                    self._stop_player()
                continue
            now = time.monotonic()
            if self._player is None or self._player.poll() is not None:
                self._player = None
                if now < self._retry_at:
                    continue
                self._start_player()
            if self._player is None:
                continue
            try:
                self._player.stdin.write(chunk)
                self._player.stdin.flush()
                self._last_audio = now
                self._warned = False
            except (BrokenPipeError, OSError, ValueError):
                self._fail_player()

    def _start_player(self):
        try:
            self._player = self._spawn(
                self._command, stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self._last_audio = time.monotonic()
        except OSError as exc:
            self._player = None
            self._fail(f"could not start aplay: {exc}")

    def _fail_player(self):
        self._stop_player()
        self._fail(f"aplay could not play on {self.device}; is another program using it?")

    def _fail(self, message):
        self._retry_at = time.monotonic() + self.RETRY_SECONDS
        if not self._warned:
            self._warned = True
            log.warning("Bluetooth audio is not reaching the speakers: %s", message)

    def _stop_player(self):
        player, self._player = self._player, None
        if player is None:
            return
        try:
            player.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            player.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            player.kill()
