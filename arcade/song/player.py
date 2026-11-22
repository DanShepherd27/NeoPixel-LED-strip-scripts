"""Plays the song through the Pi's audio output with a common CLI player."""

import logging
import shutil
import subprocess

log = logging.getLogger("arcade.song.player")

# (executable, arguments before the file name), in order of preference.
PLAYERS = (
    ("mpg123", ["-q"]),
    ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
    ("cvlc", ["--play-and-exit", "--quiet"]),
    ("mpv", ["--no-video", "--really-quiet"]),
    ("mplayer", ["-really-quiet"]),
)


def find_player():
    for name, args in PLAYERS:
        path = shutil.which(name)
        if path:
            return path, args
    return None


class PiAudioPlayer:
    def __init__(self, audio_path):
        self.audio_path = str(audio_path)
        self._process = None

    def start(self):
        """Start playback; return an error message, or None on success."""
        player = find_player()
        if player is None:
            return "No audio player found on the Pi. Install one: sudo apt install mpg123"
        path, args = player
        try:
            self._process = subprocess.Popen(
                [path, *args, self.audio_path],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            log.warning("Could not start %s: %s", path, exc)
            return "Could not start the Pi audio player: %s" % exc
        return None

    def stop(self):
        process, self._process = self._process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
