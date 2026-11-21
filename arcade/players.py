"""Player management.

Supports an unlimited number of players (bounded only by practical limits).
Each player has a unique id, a nickname, an evenly-distributed colour, a ready
status, a score and a scratch space for game-specific state.
"""

import threading
import time
import uuid
import logging

from arcade.colors import distribute_hues, player_color

log = logging.getLogger("arcade.players")


class Player:
    def __init__(self, player_id, name):
        self.id = player_id
        self.name = name
        self.join_order = time.time()
        self.hue = 0.0
        self.color = (255, 255, 255)
        self.connected = True
        self.ready = False
        self.score = 0
        self.extra = {}
        self.last_seen = time.time()

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "color": list(self.color),
            "hue": self.hue,
            "ready": self.ready,
            "score": self.score,
            "connected": self.connected,
        }


class PlayerManager:
    def __init__(self):
        self._players = {}
        self._lock = threading.RLock()

    # -- membership ---------------------------------------------------------
    def add_player(self, name):
        with self._lock:
            player_id = uuid.uuid4().hex[:12]
            player = Player(player_id, name)
            self._players[player_id] = player
            self._reassign_colors()
            log.info("Player joined: %s (%s)", name, player_id)
            return player

    def remove_player(self, player_id):
        with self._lock:
            player = self._players.pop(player_id, None)
            if player:
                self._reassign_colors()
                log.info("Player left: %s (%s)", player.name, player_id)
            return player

    def get(self, player_id):
        with self._lock:
            return self._players.get(player_id)

    def touch(self, player_id):
        """Mark a player as recently active."""
        with self._lock:
            player = self._players.get(player_id)
            if player:
                player.last_seen = time.time()
                player.connected = True

    def mark_disconnected(self, player_id):
        with self._lock:
            player = self._players.get(player_id)
            if player:
                player.connected = False

    # -- colours ------------------------------------------------------------
    def _reassign_colors(self):
        ordered = self.ordered_players()
        hues = distribute_hues(len(ordered))
        for player, hue in zip(ordered, hues):
            player.hue = hue
            player.color = player_color(hue)

    def lock_colors(self):
        """Colours are already stable by identity; provided for clarity.

        The manager recalculates hues on join/leave, so callers that need a
        stable snapshot during a game should capture it at game start.
        """

    # -- queries ------------------------------------------------------------
    def ordered_players(self):
        with self._lock:
            return sorted(self._players.values(), key=lambda p: p.join_order)

    def players(self):
        return self.ordered_players()

    def count(self):
        with self._lock:
            return len(self._players)

    def connected_players(self):
        return [p for p in self.ordered_players() if p.connected]

    def all_ready(self, min_players=1):
        connected = self.connected_players()
        return len(connected) >= min_players and all(p.ready for p in connected)

    def set_ready(self, player_id, ready):
        with self._lock:
            player = self._players.get(player_id)
            if player:
                player.ready = bool(ready)

    def reset_ready(self):
        with self._lock:
            for player in self._players.values():
                player.ready = False

    def reset_scores(self):
        with self._lock:
            for player in self._players.values():
                player.score = 0

    def prune_stale(self, timeout):
        """Drop players who have been silent for longer than ``timeout``."""
        with self._lock:
            now = time.time()
            stale = [
                pid for pid, p in self._players.items()
                if now - p.last_seen > timeout
            ]
            for pid in stale:
                p = self._players.pop(pid)
                log.info("Dropping stale player %s (%s)", p.name, pid)
            if stale:
                self._reassign_colors()
            return stale

    def snapshot(self):
        return [p.to_dict() for p in self.ordered_players()]
