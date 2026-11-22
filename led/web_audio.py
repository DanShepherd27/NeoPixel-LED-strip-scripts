"""Exclusive browser microphone lease and visualizer feature snapshots.

Raw audio remains in the browser. Only normalized volume/clap features are
sent to this process for rendering on the LED strip.
"""

import secrets
import threading
import time
import math


class WebMicQueue:
    OWNER_STALE_SECONDS = 8.0
    BAND_COUNT = 6

    def __init__(self, handoff_seconds=120):
        self._lock = threading.RLock()
        self.handoff_seconds = int(handoff_seconds)
        self._owner = None
        self._waiting = []
        self._handoff_at = None
        self._level = 0.0
        self._peak = 0.0
        self._bands = [0.0] * self.BAND_COUNT
        self._clap_until = 0.0
        self._last_update = 0.0

    def request(self, client_id, name="Guest"):
        if not isinstance(client_id, str) or not 8 <= len(client_id) <= 80:
            raise ValueError("Invalid microphone session.")
        name = " ".join(str(name or "Guest").split())[:16] or "Guest"
        with self._lock:
            self._expire_locked()
            if self._owner and self._owner["client_id"] == client_id:
                return self._client_status_locked(client_id)
            if any(item["client_id"] == client_id for item in self._waiting):
                return self._client_status_locked(client_id)
            if self._owner is None:
                self._grant_locked(client_id, name)
            else:
                self._waiting.append({"client_id": client_id, "name": name})
                if self._handoff_at is None:
                    self._handoff_at = time.monotonic() + self.handoff_seconds
            return self._client_status_locked(client_id)

    def leave(self, client_id, token=None):
        with self._lock:
            self._waiting = [item for item in self._waiting if item["client_id"] != client_id]
            if self._owner and self._owner["client_id"] == client_id:
                if token and secrets.compare_digest(self._owner["token"], token):
                    self._advance_locked()
            if not self._waiting:
                self._handoff_at = None
            return self._client_status_locked(client_id)

    def update(self, token, level, peak, clap, bands=None):
        try:
            level = max(0.0, min(1.0, float(level)))
            peak = max(0.0, min(1.0, float(peak)))
            if bands is None:
                bands = [level] * self.BAND_COUNT
            if not isinstance(bands, (list, tuple)) or len(bands) != self.BAND_COUNT:
                return False
            bands = [float(value) for value in bands]
            if any(not math.isfinite(value) for value in bands):
                return False
            bands = [max(0.0, min(1.0, value)) for value in bands]
        except (TypeError, ValueError):
            return False
        with self._lock:
            self._expire_locked()
            if not self._owner or not secrets.compare_digest(self._owner["token"], str(token or "")):
                return False
            now = time.monotonic()
            self._level, self._peak, self._bands = level, peak, bands
            if bool(clap):
                self._clap_until = now + 0.18
            self._last_update = now
            return True

    def status(self, client_id=None):
        with self._lock:
            self._expire_locked()
            return self._client_status_locked(client_id)

    def snapshot(self):
        with self._lock:
            self._expire_locked()
            fresh = self._owner is not None and time.monotonic() - self._last_update < 2.0
            return {
                "active": bool(fresh),
                "status": "listening" if fresh else "waiting",
                "level": self._level if fresh else 0.0,
                "peak": self._peak if fresh else 0.0,
                "bands": list(self._bands) if fresh else [0.0] * self.BAND_COUNT,
                "clap": fresh and time.monotonic() < self._clap_until,
                "owner": self._owner["name"] if self._owner else None,
                "queued": len(self._waiting),
            }

    def reset(self):
        with self._lock:
            self._owner = None
            self._waiting.clear()
            self._handoff_at = None
            self._level = self._peak = 0.0
            self._bands = [0.0] * self.BAND_COUNT
            self._last_update = self._clap_until = 0.0

    def _grant_locked(self, client_id, name):
        self._owner = {"client_id": client_id, "name": name, "token": secrets.token_urlsafe(32)}
        self._handoff_at = None
        self._level = self._peak = 0.0
        self._bands = [0.0] * self.BAND_COUNT
        self._last_update = self._clap_until = 0.0

    def _advance_locked(self):
        self._owner = None
        self._handoff_at = None
        if self._waiting:
            next_client = self._waiting.pop(0)
            self._grant_locked(next_client["client_id"], next_client["name"])
            if self._waiting:
                self._handoff_at = time.monotonic() + self.handoff_seconds

    def _expire_locked(self):
        now = time.monotonic()
        if self._owner and now - self._last_update > self.OWNER_STALE_SECONDS and self._last_update:
            self._advance_locked()
        if self._owner and self._waiting and self._handoff_at and now >= self._handoff_at:
            self._advance_locked()

    def _client_status_locked(self, client_id):
        is_owner = bool(self._owner and self._owner["client_id"] == client_id)
        position = next((i + 1 for i, item in enumerate(self._waiting)
                         if item["client_id"] == client_id), None)
        remaining = None
        if self._owner and self._waiting and self._handoff_at:
            remaining = max(0, int(self._handoff_at - time.monotonic() + 0.999))
        return {
            "role": "owner" if is_owner else ("queued" if position else "idle"),
            "position": position,
            "token": self._owner["token"] if is_owner else None,
            "owner": self._owner["name"] if self._owner else None,
            "queued": len(self._waiting),
            "handoff_in": remaining,
        }
