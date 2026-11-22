"""Plays the song through the Pi's audio output with a common CLI player."""

import logging
import os
import shutil
import subprocess
import threading

log = logging.getLogger("arcade.song.player")

# One MP3 frame: seeking with mpg123 works in whole frames (1152 samples at 44.1 kHz).
FRAME_SECONDS = 1152 / 44100


def snap_to_frame(seconds):
    """The nearest earlier point every player can start from exactly."""
    return int(max(0.0, seconds) / FRAME_SECONDS) * FRAME_SECONDS


# (executable, base arguments, ALSA device -> arguments, start offset -> arguments),
# in order of preference. ffplay has no ALSA device option, so it uses the
# SDL environment instead (see PiAudioPlayer.start).
PLAYERS = (
    ("mpg123", ["-q"], lambda device: ["-a", device],
     lambda seconds: ["-k", str(round(seconds / FRAME_SECONDS))]),
    ("mpv", ["--no-video", "--really-quiet"], lambda device: ["--audio-device=alsa/" + device],
     lambda seconds: ["--start=%.3f" % seconds]),
    ("cvlc", ["--play-and-exit", "--quiet"], lambda device: ["--alsa-audio-device", device],
     lambda seconds: ["--start-time=%.3f" % seconds]),
    ("mplayer", ["-really-quiet"], lambda device: ["-ao", "alsa:device=" + device.replace(":", "=")],
     lambda seconds: ["-ss", "%.3f" % seconds]),
    ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"], lambda device: [],
     lambda seconds: ["-ss", "%.3f" % seconds]),
)


def output_device(device):
    """The microphone's ALSA device as an output device ("hw:" gains format conversion)."""
    if not device or device == "default":
        return None
    return "plug" + device if device.startswith("hw:") else device


def find_player():
    for name, args, device_args, offset_args in PLAYERS:
        if name == "cvlc" and os.geteuid() == 0:
            continue  # VLC refuses to run as root, and the service runs as root
        path = shutil.which(name)
        if path:
            return name, path, args, device_args, offset_args
    return None


class PiAudioPlayer:
    def __init__(self, audio_path, device=None):
        self.audio_path = str(audio_path)
        self.device = output_device(device)
        self._process = None
        self.last_error = None

    def start(self, offset=0.0):
        """Start playback at ``offset`` seconds (see snap_to_frame); return an
        error message, or None on success."""
        player = find_player()
        if player is None:
            return "No audio player found on the Pi. Install one: sudo apt install mpg123"
        name, path, args, device_args, offset_args = player
        if offset > 0:
            args = args + offset_args(offset)
        env = None
        if self.device:
            args = args + device_args(self.device)
            if name == "ffplay":
                env = dict(os.environ, SDL_AUDIODRIVER="alsa", AUDIODEV=self.device)
        log.info("Song audio: %s on %s", name, self.device or "default output")
        try:
            self._process = subprocess.Popen(
                [path, *args, self.audio_path], env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, text=True,
            )
            threading.Thread(target=self._log_errors, args=(self._process,), daemon=True).start()
        except OSError as exc:
            log.warning("Could not start %s: %s", path, exc)
            return "Could not start the Pi audio player: %s" % exc
        return None

    def _log_errors(self, process):
        """Keep the player's last error line so a silent failure is visible."""
        for line in process.stderr:
            line = line.strip()
            if line:
                self.last_error = line
                log.warning("Song player: %s", line)

    def failure(self):
        """Message if the player exited early (it normally runs for the whole song)."""
        process = self._process
        if process is not None and process.poll() not in (None, 0):
            return "Pi audio player stopped (exit %s): %s" % (
                process.returncode, self.last_error or "no details")
        return None

    def stop(self):
        process, self._process = self._process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
