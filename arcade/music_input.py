"""Which audio source drives the sound-reactive lighting, mixed into the arcade manager.

The host owns the lifecycle and the lock; this module owns the registered sources
(see ``led.audio_sources``) and which one is selected.
"""

import logging

from arcade.live_beat import LiveBeatTracker
from arcade.music_gain import AutoGain
from arcade.song.engine import FlashGuard

log = logging.getLogger("arcade.music_input")


class MusicInputMixin:
    def _init_music_input(self, sources, selected):
        self.music_sources = {source.name: source for source in sources}
        self.music_input = selected if selected in self.music_sources else next(iter(self.music_sources))

    @property
    def _music_source(self):
        return self.music_sources[self.music_input]

    @property
    def bluetooth_latency_ms(self):
        source = self.music_sources.get("bluetooth")
        return source.delay_ms if source else 0

    @bluetooth_latency_ms.setter
    def bluetooth_latency_ms(self, milliseconds):
        source = self.music_sources.get("bluetooth")
        if source:
            source.delay_ms = int(milliseconds)

    @property
    def bluetooth_auto_sync(self):
        sync = self._bluetooth_sync
        return bool(sync and sync.enabled)

    @bluetooth_auto_sync.setter
    def bluetooth_auto_sync(self, enabled):
        sync = self._bluetooth_sync
        if sync:
            sync.enabled = bool(enabled)

    @property
    def _bluetooth_sync(self):
        source = self.music_sources.get("bluetooth")
        return getattr(source, "sync", None)

    def set_music_input(self, name):
        """Switch the sound-reactive source live; the tempo and gain start over for it."""
        if name not in self.music_sources:
            raise ValueError("Choose one of the available sound sources.")
        with self._lock:
            if name == self.music_input:
                return
            self._music_source.deactivate()
            self.music_input = name
            self._reset_music_tracking()
            self._music_gain = AutoGain(7)
            self._music_source.reset()
            if self.state.value == "music":
                self._music_source.activate()
            log.info("Sound-reactive source -> %s", name)

    def music_input_snapshot(self):
        return {
            "selected": self.music_input,
            "sources": [{"name": source.name, "label": source.label}
                        for source in self.music_sources.values()],
            "bluetooth_latency_ms": self.bluetooth_latency_ms,
            "bluetooth_sync": (self._bluetooth_sync.describe() if self._bluetooth_sync
                               else {"enabled": False, "state": "off", "score": None}),
        }

    def _reset_music_tracking(self):
        self._music_beat = LiveBeatTracker()
        self._music_ctx = self._music_beat.ctx
        self._beat_pattern_state = {}
        self._music_flash_guard = FlashGuard()

    def _deactivate_music_sources(self):
        for source in self.music_sources.values():
            source.deactivate()
