"""The arcade manager.

Owns the lifecycle state machine (idle -> lobby -> countdown -> game ->
results -> idle), the player manager, the idle-effect rotation and the active
game. It is also the *scene* the central renderer drives every frame: all game
logic and pixel rendering is funnelled through :meth:`render`.
"""

import threading
import queue
import random
import logging

from arcade.state import ArcadeState
from arcade.players import PlayerManager
from arcade.games import GAMES, game_catalog
from led.effects import EFFECTS
from led.colors import hsv_to_rgb

from config import (
    LED_COUNT,
    IDLE_ANIMATION_DURATION,
    IDLE_RANDOM_ORDER,
    COUNTDOWN_SECONDS,
    RESULTS_DURATION,
    LED_ORIENTATION,
)

log = logging.getLogger("arcade.manager")


class ArcadeManager:
    def __init__(self, count=LED_COUNT, audio_input=None):
        self.count = count
        self.audio_input = audio_input
        self.state = ArcadeState.IDLE
        self.players = PlayerManager()

        # Idle effect rotation.
        self._idle_effects = [(name, cls(count)) for name, cls in EFFECTS]
        self._idle_order = list(range(len(self._idle_effects)))
        if IDLE_RANDOM_ORDER:
            random.shuffle(self._idle_order)
        self._idle_pos = 0
        self._idle_timer = IDLE_ANIMATION_DURATION
        self.current_idle_name = self._idle_effects[self._idle_order[0]][0]

        # Game selection / instance.
        self.selected_game = None
        self.game = None
        self.game_class = None

        # Lifecycle timers.
        self.countdown = 0.0
        self.results_timer = 0.0
        self.tutorial_index = 0
        self.tutorial_elapsed = 0.0

        self._lock = threading.RLock()
        self._input_queue = queue.Queue()

    # -- current idle effect -------------------------------------------------
    @property
    def current_effect(self):
        return self._idle_effects[self._idle_order[self._idle_pos]][1]

    def _next_idle(self):
        self._idle_pos = (self._idle_pos + 1) % len(self._idle_effects)
        self._idle_timer = IDLE_ANIMATION_DURATION
        self.current_idle_name = self._idle_effects[self._idle_order[self._idle_pos]][0]
        log.info("Idle animation: %s", self.current_idle_name)

    # -- public control API (thread-safe, called from web layer) ------------
    def join_player(self, name):
        with self._lock:
            if self.state == ArcadeState.MUSIC:
                self.stop_music_mode()
            player = self.players.add_player(name)
            if self.state == ArcadeState.IDLE:
                self._enter_lobby()
            return player

    def leave_player(self, player_id):
        with self._lock:
            self.players.remove_player(player_id)
            if self.state == ArcadeState.LOBBY and self.players.count() == 0:
                self._enter_idle()

    def touch(self, player_id):
        self.players.touch(player_id)

    def mark_disconnected(self, player_id):
        self.players.mark_disconnected(player_id)

    def set_ready(self, player_id, ready):
        self.players.set_ready(player_id, ready)

    def select_game(self, slug):
        with self._lock:
            if slug in GAMES and self.state == ArcadeState.LOBBY:
                self.selected_game = slug
                log.info("Game selected: %s", slug)

    def start_music_mode(self):
        with self._lock:
            if self.state == ArcadeState.MUSIC:
                return True
            if self.state != ArcadeState.IDLE or self.audio_input is None:
                return False
            self.selected_game = None
            self.game = None
            self.game_class = None
            self.audio_input.set_enabled(True)
            self.state = ArcadeState.MUSIC
            log.info("State -> MUSIC (microphone visualizer)")
            return True

    def stop_music_mode(self):
        with self._lock:
            if self.audio_input is not None:
                self.audio_input.set_enabled(False)
            if self.state == ArcadeState.MUSIC:
                self.state = ArcadeState.IDLE
                log.info("State -> IDLE (music visualizer stopped)")

    def start_game(self):
        with self._lock:
            if self.state == ArcadeState.LOBBY and self.selected_game:
                self._enter_tutorial()

    def rematch(self):
        with self._lock:
            if self.state == ArcadeState.RESULTS and self.selected_game:
                self._enter_tutorial()

    def skip_tutorial(self):
        with self._lock:
            if self.state == ArcadeState.TUTORIAL:
                self._enter_countdown()

    def return_to_idle(self):
        with self._lock:
            self._enter_idle(clear_players=True)

    def stop_game(self):
        with self._lock:
            if self.state in (ArcadeState.GAME, ArcadeState.COUNTDOWN,
                              ArcadeState.TUTORIAL,
                              ArcadeState.RESULTS):
                self._enter_idle(clear_players=True)

    def set_brightness(self, brightness):
        # Applied by the hardware; kept here for the admin API to route through.
        return brightness

    def handle_input(self, player_id, action):
        """Queue a player input; processed by the render loop next frame."""
        self._input_queue.put((player_id, action))

    # -- lifecycle transitions (must hold self._lock) ------------------------
    def _enter_idle(self, clear_players=True):
        if self.audio_input is not None:
            self.audio_input.set_enabled(False)
        if clear_players:
            for p in list(self.players.players()):
                self.players.remove_player(p.id)
        self.game = None
        self.game_class = None
        self.selected_game = None
        self.countdown = 0.0
        self.tutorial_index = 0
        self.tutorial_elapsed = 0.0
        self.state = ArcadeState.IDLE
        log.info("State -> IDLE")

    def _enter_lobby(self):
        self.state = ArcadeState.LOBBY
        self.selected_game = None
        self.players.reset_ready()
        log.info("State -> LOBBY")

    def _enter_countdown(self):
        self.state = ArcadeState.COUNTDOWN
        self.countdown = COUNTDOWN_SECONDS
        self.players.reset_ready()
        log.info("State -> COUNTDOWN (%s)", self.selected_game)

    def _enter_tutorial(self):
        self.game_class = GAMES[self.selected_game]
        self.game = self.game_class(self)
        self.game.setup(self._participants())
        self.tutorial_index = 0
        self.tutorial_elapsed = 0.0
        self.state = ArcadeState.TUTORIAL
        log.info("State -> TUTORIAL (%s)", self.selected_game)

    def _start_game(self):
        if self.game is None or self.game_class is None:
            self.game_class = GAMES[self.selected_game]
            self.game = self.game_class(self)
            self.game.setup(self._participants())
        self.game.start()
        self.state = ArcadeState.GAME
        log.info("State -> GAME (%s) with %d players",
                 self.game.name, len(self.game.players))

    def _enter_results(self):
        self.state = ArcadeState.RESULTS
        self.results_timer = RESULTS_DURATION
        log.info("State -> RESULTS (winner=%s)", self.game.winner)

    def _participants(self):
        """Pick the players for the current game based on its constraints."""
        connected = self.players.connected_players()
        if not connected:
            connected = self.players.players()
        limit = self.game_class.max_players
        if limit is not None:
            connected = connected[:limit]
        return connected

    # -- per-frame update / render (called by the renderer thread) ----------
    def _process_inputs(self):
        while True:
            try:
                player_id, action = self._input_queue.get_nowait()
            except queue.Empty:
                break
            self.players.touch(player_id)
            if self.state == ArcadeState.GAME and self.game is not None:
                try:
                    self.game.handle_input(player_id, action)
                except Exception:
                    log.exception("Game input handler failed")

    def render(self, frame, dt):
        with self._lock:
            self._process_inputs()

            if self.state == ArcadeState.IDLE:
                self._update_idle(dt)
                self.current_effect.render(frame, dt)
            elif self.state == ArcadeState.LOBBY:
                self._render_lobby(frame, dt)
            elif self.state == ArcadeState.MUSIC:
                self._render_music(frame, dt)
            elif self.state == ArcadeState.TUTORIAL:
                self._update_tutorial(dt)
                if self.state == ArcadeState.TUTORIAL and self.game is not None:
                    steps = self.game_class.tutorial_steps
                    step = steps[self.tutorial_index]
                    self.game.render_tutorial(
                        frame, self.tutorial_index, self.tutorial_elapsed,
                        step["duration"],
                    )
            elif self.state == ArcadeState.COUNTDOWN:
                self._update_countdown(dt)
                self._render_countdown(frame, dt)
            elif self.state == ArcadeState.GAME:
                self._update_game(dt)
                if self.game is not None:
                    self.game.render(frame, dt)
            elif self.state == ArcadeState.RESULTS:
                self._update_results(dt)
                self._render_results(frame, dt)

    # -- state updates -------------------------------------------------------
    def _update_idle(self, dt):
        self._idle_timer -= dt
        if self._idle_timer <= 0:
            self._next_idle()

    def _render_music(self, frame, dt):
        audio = self.audio_input.snapshot() if self.audio_input else {}
        level = float(audio.get("level", 0.0))
        half = (self.count + 1) // 2
        extent = int(round(level * max(0, half - 1)))

        # Show a dim center marker when the room is quiet, then expand outward
        # as microphone energy rises. Hue shifts from cool to warm with level.
        for offset in range(max(1, extent + 1)):
            strength = max(0.18, 1.0 - offset / max(2.0, extent + 1.0) * 0.65)
            hue = 205.0 - 185.0 * level + offset * 2.5
            color = hsv_to_rgb(hue, 0.9, strength * (0.28 + level * 0.72))
            left = half - 1 - offset
            right = half + offset
            frame.set(left, color)
            frame.set(right, color)

        if audio.get("clap"):
            self._music_clap_flash = 0.20
        else:
            self._music_clap_flash = max(0.0, getattr(self, "_music_clap_flash", 0.0) - dt)
        if self._music_clap_flash > 0:
            amount = min(1.0, self._music_clap_flash / 0.20)
            for index in range(frame.count):
                frame.blend(index, (255, 255, 255), amount)

    def _update_tutorial(self, dt):
        steps = self.game_class.tutorial_steps
        self.tutorial_elapsed += dt
        while self.tutorial_index < len(steps):
            duration = float(steps[self.tutorial_index]["duration"])
            if self.tutorial_elapsed < duration:
                return
            self.tutorial_elapsed -= duration
            self.tutorial_index += 1
        self._enter_countdown()

    def _update_countdown(self, dt):
        self.countdown -= dt
        if self.countdown <= 0:
            self._start_game()

    def _update_game(self, dt):
        if self.game is None:
            self._enter_idle(clear_players=False)
            return
        self.game.update(dt)
        if self.game.finished:
            self._enter_results()

    def _update_results(self, dt):
        self.results_timer -= dt
        if self.results_timer <= 0:
            self._enter_idle(clear_players=True)

    # -- rendering helpers ---------------------------------------------------
    def _render_lobby(self, frame, dt):
        players = self.players.connected_players()
        if not players:
            self.current_effect.render(frame, dt)
            return
        import math
        import time as _time
        n = len(players)
        segment = self.count / n
        pulse = (math.sin(_time.monotonic() * 3.0) + 1.0) / 2.0
        for i, player in enumerate(players):
            start = int(i * segment)
            end = int((i + 1) * segment)
            brightness = 0.35 + 0.65 * pulse if player.ready else 0.25
            r, g, b = player.color
            color = (int(r * brightness), int(g * brightness), int(b * brightness))
            for j in range(start, min(end, self.count)):
                frame.set(j, color)

    def _render_countdown(self, frame, dt):
        import time as _time
        remaining = max(0.0, self.countdown)
        whole = int(remaining) + 1  # 3, 2, 1, (0 -> GO)
        blink = (int(_time.monotonic() * 4.0) % 2 == 0)
        if whole <= 0:
            frame.fill((255, 255, 255))
            return
        colors = {3: (200, 40, 40), 2: (220, 180, 40), 1: (40, 200, 80)}
        color = colors.get(whole, (255, 255, 255))
        if blink:
            # Fill a shrinking fraction as the countdown approaches zero.
            frac = remaining / COUNTDOWN_SECONDS
            lit = int(self.count * max(0.15, frac))
            for i in range(lit):
                frame.set(i, color)

    def _render_results(self, frame, dt):
        import math
        import time as _time
        winner = None
        if self.game is not None and self.game.winner:
            winner = self.players.get(self.game.winner)
        color = winner.color if winner else (255, 255, 255)
        pulse = (math.sin(_time.monotonic() * 5.0) + 1.0) / 2.0
        r, g, b = color
        frame.fill((int(r * pulse), int(g * pulse), int(b * pulse)))

    # -- web snapshot --------------------------------------------------------
    def get_state(self):
        with self._lock:
            game_state = None
            if self.game is not None:
                game_state = self.game.get_state()
                if self.game.winner:
                    winner = self.players.get(self.game.winner)
                    game_state["winner_name"] = winner.name if winner else None
                    game_state["winner_color"] = list(winner.color) if winner else None

            return {
                "state": self.state.value,
                "players": self.players.snapshot(),
                "idle_animation": self.current_idle_name,
                "led_orientation": LED_ORIENTATION,
                "games": game_catalog(),
                "selected_game": self.selected_game,
                "countdown": round(max(0.0, self.countdown), 1),
                "tutorial": self._tutorial_snapshot(),
                "audio": self.audio_input.snapshot() if self.audio_input else {
                    "status": "unavailable", "error": "No audio input configured.",
                    "level": 0.0, "peak": 0.0, "clap": False,
                },
                "game": game_state,
                "results": self.game.results if self.game else None,
            }

    def _tutorial_snapshot(self):
        if self.state != ArcadeState.TUTORIAL or self.game_class is None:
            return None
        steps = self.game_class.tutorial_steps
        if not steps:
            return {"index": 0, "count": 0, "title": "Get ready",
                    "instruction": "The game is about to begin.", "remaining": 0.0}
        step = steps[self.tutorial_index]
        return {
            "index": self.tutorial_index + 1,
            "count": len(steps),
            "title": step["title"],
            "instruction": step["instruction"],
            "remaining": round(max(0.0, float(step["duration"]) - self.tutorial_elapsed), 1),
        }
