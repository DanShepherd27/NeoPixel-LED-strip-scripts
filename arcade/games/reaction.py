"""Reaction Race — a competitive reaction-time game.

Players watch the LED strip. After a random delay a bright signal appears and
each player must press their button as fast as possible. Reaction times are
recorded; false starts are penalised. The lowest total reaction time wins.
"""

import random
import time
import math

from led.colors import dim

from arcade.games.base import BaseGame


class ReactionGame(BaseGame):
    name = "Reaction Race"
    slug = "reaction"
    description = "Hit your button the instant the lights flash!"
    min_players = 1
    max_players = None

    ROUNDS = 3
    MIN_DELAY = 1.5
    MAX_DELAY = 4.0
    ROUND_TIMEOUT = 3.0
    ROUND_PAUSE = 2.5
    FALSE_START_PENALTY = 3.0  # seconds added to a false-starter's time
    tutorial_steps = (
        {"title": "Wait for the flash", "instruction": "Keep your hands off the button while the strip pulses.", "duration": 4.5},
        {"title": "Tap on white", "instruction": "Press only when the whole strip flashes white.", "duration": 4.5},
    )

    def __init__(self, manager):
        super().__init__(manager)
        self.round = 0
        self.phase = "waiting"          # waiting | signal | round_over
        self.signal_at = 0.0
        self.delay = 0.0
        self.times = {}                 # player_id -> list of round times
        self.false_starts = {}          # player_id -> count
        self.round_times = {}           # player_id -> ms for current round
        self.round_winner = None
        self._wait_timer = 0.0
        self._round_timer = 0.0

    def setup(self, players):
        super().setup(players)
        self.round = 0
        self.times = {p.id: [] for p in self.players}
        self.false_starts = {p.id: 0 for p in self.players}

    def start(self):
        super().start()
        self._begin_round()

    def _begin_round(self):
        self.round += 1
        self.phase = "waiting"
        self.delay = random.uniform(self.MIN_DELAY, self.MAX_DELAY)
        self._wait_timer = self.delay
        self.round_times = {}
        self.round_winner = None

    def _signal(self):
        self.phase = "signal"
        self.signal_at = time.monotonic()

    def update(self, dt):
        super().update(dt)
        if not self.running:
            return

        if self.phase == "waiting":
            self._wait_timer -= dt
            if self._wait_timer <= 0:
                self._signal()
        elif self.phase == "signal":
            # Everyone responded, or the round timed out.
            if len(self.round_times) >= len(self.players):
                self._finish_round()
            elif time.monotonic() - self.signal_at >= self.ROUND_TIMEOUT:
                # Players who never pressed get a large time.
                for p in self.players:
                    if p.id not in self.round_times:
                        self.round_times[p.id] = self.ROUND_TIMEOUT * 1000
                self._finish_round()
        elif self.phase == "round_over":
            self._round_timer -= dt
            if self._round_timer <= 0:
                if self.round >= self.ROUNDS:
                    self._finish_game()
                else:
                    self._begin_round()

    def handle_input(self, player_id, action):
        if not self.running or action != "press":
            return
        if self.phase == "waiting":
            # False start.
            self.false_starts[player_id] = self.false_starts.get(player_id, 0) + 1
            self.round_times.setdefault(
                player_id, (self.FALSE_START_PENALTY) * 1000)
        elif self.phase == "signal" and player_id not in self.round_times:
            ms = (time.monotonic() - self.signal_at) * 1000.0
            self.round_times[player_id] = round(ms, 1)

    def _finish_round(self):
        self.phase = "round_over"
        for p in self.players:
            t = self.round_times.get(p.id, self.ROUND_TIMEOUT * 1000)
            self.times[p.id].append(t)

        if self.players and self.round_times:
            self.round_winner = min(
                self.round_times, key=lambda pid: self.round_times[pid]
            )

        self._round_timer = self.ROUND_PAUSE

    def _finish_game(self):
        totals = {p.id: sum(self.times[p.id]) for p in self.players}
        self.winner = min(totals, key=lambda pid: totals[pid])
        for p in self.players:
            p.score = -totals[p.id]  # higher (closer to 0) is better
        self.results = {
            "reaction_times_ms": {p.id: self.times[p.id] for p in self.players},
            "totals_ms": {p.id: round(totals[p.id], 1) for p in self.players},
            "false_starts": dict(self.false_starts),
        }
        self.end()

    def render(self, frame, dt):
        if self.phase == "signal":
            frame.fill((255, 255, 255))
        elif self.phase == "round_over" and self.round_winner:
            player = self.manager.players.get(self.round_winner)
            frame.fill(player.color if player else (255, 255, 255))
        else:
            # Waiting: dim pulsing colour so the strip stays alive.
            pulse = (math.sin(time.monotonic() * 4.0) + 1.0) / 2.0
            frame.fill(dim((80, 80, 160), 0.3 + 0.3 * pulse))

    def render_tutorial(self, frame, step_index, elapsed, duration):
        if step_index == 0:
            import math
            pulse = 0.18 + 0.32 * (math.sin(elapsed * 4.0) + 1.0) / 2.0
            color = tuple(int(90 * pulse) for _ in range(3))
            frame.fill(color)
        else:
            frame.fill((255, 255, 255) if int(elapsed * 3.0) % 2 == 0 else (12, 12, 24))

    def get_state(self):
        state = super().get_state()
        state.update({
            "phase": self.phase,
            "round": self.round,
            "rounds": self.ROUNDS,
            "round_winner": self.round_winner,
        })
        return state
