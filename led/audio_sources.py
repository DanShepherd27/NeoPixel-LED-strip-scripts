"""Inputs for the sound-reactive lighting, behind one interface.

The renderer asks the selected ``AudioSource`` for features and kick/snare onsets and
never needs to know where the sound comes from. To add an input (line-in, a network
stream, ...), subclass ``AudioSource`` and register an instance with the manager.
"""

import abc
import collections
import time

BAND_COUNT = 6
SILENT = {"level": 0.0, "peak": 0.0, "bands": [0.0] * BAND_COUNT, "clap": False, "active": False}


class AudioSource(abc.ABC):
    name = ""     # stable id used in settings and the API
    label = ""    # what people see in the UI

    @abc.abstractmethod
    def activate(self):
        """Start capturing; called when sound-reactive lighting uses this source."""

    @abc.abstractmethod
    def deactivate(self):
        """Stop capturing and release the device."""

    @abc.abstractmethod
    def features(self):
        """Current ``level``, ``peak``, six ``bands`` and ``clap``. Called once per rendered frame."""

    @abc.abstractmethod
    def take_onsets(self):
        """Kick/snare onsets since the last call: ``(monotonic time the sound was heard,
        "kick" or "snare", strength 0-1)``."""

    @abc.abstractmethod
    def describe(self):
        """Status for the UI (``status``, ``error``, meters, ``source``); never changes state."""

    def reset(self):
        """Forget onsets heard before a restart or a switch to this source."""
        self.take_onsets()


class MicrophoneSource(AudioSource):
    """The browser microphone that holds the lease, with the Pi's own microphone as fallback."""

    name = "microphone"
    label = "Microphone"

    def __init__(self, web_mics, pi_input=None):
        self._web = web_mics
        self._pi = pi_input
        self._pi_listening = False
        self._web_active = False

    def activate(self):
        self._set_pi_listening(True)

    def deactivate(self):
        self._set_pi_listening(False)
        self._web.reset()

    def features(self):
        web = self._web.snapshot()
        self._web_active = web["active"]
        self._follow_browser(web["active"])
        if web["active"]:
            return web
        return self._pi.snapshot() if self._pi is not None else dict(SILENT)

    def take_onsets(self):
        onsets = {"web": self._web.take_onsets(),
                  "pi": self._pi.take_onsets() if self._pi is not None else []}
        return onsets["web" if self._web_active else "pi"]

    def describe(self):
        web = self._web.snapshot()
        if web["active"]:
            return dict(web, source="web")
        if self._pi is not None:
            return dict(self._pi.snapshot(), source="pi")
        return {"status": "unavailable", "error": "No audio input configured.",
                "level": 0.0, "peak": 0.0, "clap": False, "source": "none"}

    def _follow_browser(self, browser_active):
        """The Pi microphone listens only while no browser microphone does."""
        self._set_pi_listening(not browser_active, force=False)

    def _set_pi_listening(self, listening, force=True):
        if self._pi is not None and (force or self._pi_listening != listening):
            self._pi.set_enabled(listening)
            self._pi_listening = listening


class DelayedFeed:
    """Holds features and onsets back so the lights land when the sound leaves the speakers.

    A source that is analyzed before it is played (Bluetooth) is ahead of what people
    hear by the playback delay. Onsets are released, stamped with the time they become
    audible, once that moment arrives.
    """

    def __init__(self):
        self.clear()

    def clear(self):
        self._frames = collections.deque()
        self._pending = []
        self._shown = dict(SILENT)

    def advance(self, now, features, onsets, delay):
        """Add this frame's input; return ``(features to show now, onsets that are audible now)``."""
        self._frames.append((now, features))
        self._pending.extend((heard + delay, name, strength) for heard, name, strength in onsets)
        while self._frames and self._frames[0][0] <= now - delay:
            self._shown = self._frames.popleft()[1]
        audible = sorted(item for item in self._pending if item[0] <= now)
        self._pending = [item for item in self._pending if item[0] > now]
        return self._shown, audible


class DelaySync(abc.ABC):
    """Keeps a source's playback delay matched to the speakers while it plays."""

    @abc.abstractmethod
    def start(self):
        """The source became active: begin listening."""

    @abc.abstractmethod
    def stop(self):
        """The source stopped: release anything ``start`` took."""

    @abc.abstractmethod
    def update(self, delay_ms):
        """Called every frame with the current delay; returns the delay to use."""

    @abc.abstractmethod
    def describe(self):
        """Status for the UI: ``enabled``, ``state`` and the last match ``score``."""


class BluetoothSource(AudioSource):
    """Audio a phone streams to the Pi over Bluetooth, analyzed before it reaches the speakers."""

    name = "bluetooth"
    label = "Bluetooth (phone audio)"

    def __init__(self, capture, delay_ms=0, sync=None):
        self._capture = capture
        self.delay_ms = int(delay_ms)    # speaker playback delay the lights are held back by
        self.sync = sync                 # optional DelaySync that measures that delay live
        self._feed = DelayedFeed()
        self._audible = []

    def activate(self):
        self._capture.set_enabled(True)
        if self.sync is not None:
            self.sync.start()

    def deactivate(self):
        self._capture.set_enabled(False)
        if self.sync is not None:
            self.sync.stop()
        self._feed.clear()
        self._audible = []

    def features(self):
        if self.sync is not None:
            self.delay_ms = int(round(self.sync.update(self.delay_ms)))
        shown, audible = self._feed.advance(
            time.monotonic(), self._capture.snapshot(), self._capture.take_onsets(),
            self.delay_ms / 1000.0,
        )
        self._audible.extend(audible)
        return shown

    def take_onsets(self):
        audible, self._audible = self._audible, []
        return audible

    def describe(self):
        sync = self.sync.describe() if self.sync is not None else {"enabled": False, "state": "off"}
        return dict(self._capture.snapshot(), source=self.name, delay_ms=self.delay_ms, sync=sync)

    def reset(self):
        self._capture.take_onsets()
        self._feed.clear()
        self._audible = []
