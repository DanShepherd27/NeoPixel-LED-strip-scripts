"""Strip Pong — a two-player, one-dimensional Pong game.

A ball travels along the strip. Each player guards one end and must hit the
ball while it is inside their hit zone. A successful hit reverses the ball and
increases its speed; a miss gives the opponent a point. First to the target
score wins.
"""

import random

from led.colors import hsv_to_rgb, blend, dim

from arcade.games.base import BaseGame


class PongGame(BaseGame):
    name = "Pong"
    slug = "pong"
    description = "Hit the ball before it reaches your end!"
    min_players = 2
    max_players = 2

    WIN_SCORE = 5
    HIT_ZONE = 4            # LEDs from each end considered the hit zone
    START_SPEED = 20.0
    MAX_SPEED = 60.0
    SPEEDUP = 4.0           # LEDs/sec added per hit
    tutorial_steps = (
        {"title": "Guard your end", "instruction": "Each player protects one end of the strip.", "duration": 2.6},
        {"title": "Tap HIT in the zone", "instruction": "Tap as the ball enters your dim end zone to send it back.", "duration": 2.6},
    )

    def __init__(self, manager):
        super().__init__(manager)
        self.ball = 0.0
        self.direction = 1
        self.speed = self.START_SPEED
        self.scores = {}
        self.last_hit_by = None
        self._flash = 0.0

    def setup(self, players):
        super().setup(players)
        self.players = players[:2]
        self.scores = {p.id: 0 for p in self.players}

    def start(self):
        super().start()
        self.speed = self.START_SPEED
        self.scores = {p.id: 0 for p in self.players}
        self._reset_ball()

    def _reset_ball(self):
        center = (self.manager.count - 1) / 2.0
        self.ball = center
        self.direction = random.choice([-1, 1])
        self.last_hit_by = None

    def update(self, dt):
        super().update(dt)
        if not self.running:
            return

        self._flash = max(0.0, self._flash - dt)
        self.ball += self.direction * self.speed * dt

        # Ball reached the left end: right player scores.
        if self.ball <= 0:
            if len(self.players) >= 2:
                self.scores[self.players[1].id] += 1
            self._flash = 0.6
            self._check_win()
            if self.running:
                self._reset_ball()
        elif self.ball >= self.manager.count - 1:
            if len(self.players) >= 2:
                self.scores[self.players[0].id] += 1
            self._flash = 0.6
            self._check_win()
            if self.running:
                self._reset_ball()

    def handle_input(self, player_id, action):
        if not self.running or action != "hit":
            return

        # Determine which end this player guards.
        if len(self.players) < 2:
            return
        left_id, right_id = self.players[0].id, self.players[1].id

        if player_id == left_id:
            # Left player can only hit a ball moving left, within the left zone.
            if self.direction == -1 and self.ball <= self.HIT_ZONE:
                self.direction = 1
                self._speed_up(player_id)
        elif player_id == right_id:
            if self.direction == 1 and self.ball >= self.manager.count - 1 - self.HIT_ZONE:
                self.direction = -1
                self._speed_up(player_id)

    def _speed_up(self, player_id):
        self.speed = min(self.MAX_SPEED, self.speed + self.SPEEDUP)
        self.last_hit_by = player_id

    def _check_win(self):
        for pid, score in self.scores.items():
            if score >= self.WIN_SCORE:
                self.winner = pid
                self.results = {"scores": dict(self.scores)}
                for p in self.players:
                    p.score = self.scores.get(p.id, 0)
                self.end()

    def render(self, frame, dt):
        # Hit zones.
        for i in range(self.HIT_ZONE):
            if i < frame.count:
                frame.set(i, dim((40, 40, 120), 0.6))
            j = frame.count - 1 - i
            if j >= 0:
                frame.set(j, dim((120, 40, 40), 0.6))

        # Ball.
        idx = int(round(self.ball))
        if 0 <= idx < frame.count:
            frame.set(idx, (255, 255, 255))

        # Player markers at each end.
        if len(self.players) >= 1:
            frame.set(0, self.players[0].color)
        if len(self.players) >= 2:
            frame.set(frame.count - 1, self.players[1].color)

        # Score flash on a score.
        if self._flash > 0:
            for i in range(frame.count):
                frame.blend(i, (255, 255, 255), self._flash * 0.4)

    def render_tutorial(self, frame, step_index, elapsed, duration):
        zone = min(self.HIT_ZONE, frame.count // 3)
        for i in range(zone):
            frame.set(i, (30, 50, 170))
            frame.set(frame.count - 1 - i, (170, 40, 50))
        span = max(1, frame.count - 1)
        phase = (elapsed * 0.45) % 2.0
        ball = phase * span if phase <= 1.0 else (2.0 - phase) * span
        frame.set(int(round(ball)), (255, 255, 255))

    def get_state(self):
        state = super().get_state()
        state.update({
            "scores": dict(self.scores),
            "ball": round(self.ball, 1),
            "speed": round(self.speed, 1),
        })
        return state
