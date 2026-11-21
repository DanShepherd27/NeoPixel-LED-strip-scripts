"""Dodge / Obstacle Survival.

A player controls an avatar that moves along the strip while obstacles sweep
across it. The avatar must avoid them; collisions cost lives, and the game
speeds up over time. Score is survival time.
"""

import random
import math

from led.colors import hsv_to_rgb, blend, dim

from arcade.games.base import BaseGame


class DodgeGame(BaseGame):
    name = "Dodge"
    slug = "dodge"
    description = "Move your avatar to dodge the incoming obstacles!"
    min_players = 1
    max_players = 1

    START_LIVES = 3
    AVATAR_SPEED = 28.0      # LEDs/second while a direction is held
    SPAWN_INTERVAL = 1.2
    BASE_SPEED = 8.0         # LEDs/second
    MAX_SPEED = 30.0
    SPEEDUP = 0.35           # LEDs/sec added per second
    INVULN_TIME = 1.5
    tutorial_steps = (
        {"title": "Move to dodge", "instruction": "Hold LEFT or RIGHT to move your colored LED.", "duration": 2.6},
        {"title": "Avoid red lights", "instruction": "Incoming red LEDs are obstacles. Survive with three lives.", "duration": 2.6},
    )

    def __init__(self, manager):
        super().__init__(manager)
        self.avatar = 30.0
        self.move_dir = 0
        self.lives = self.START_LIVES
        self.obstacles = []
        self._spawn_timer = 0.0
        self._invuln = 0.0
        self._hit_flash = 0.0
        self.score = 0.0

    def setup(self, players):
        super().setup(players)

    def start(self):
        super().start()
        self.avatar = 30.0
        self.move_dir = 0
        self.lives = self.START_LIVES
        self.obstacles = []
        self._spawn_timer = 1.0
        self._invuln = 0.0
        self._hit_flash = 0.0
        self.score = 0.0

    def _speed(self):
        return min(self.MAX_SPEED, self.BASE_SPEED + self.elapsed * self.SPEEDUP)

    def update(self, dt):
        super().update(dt)
        if not self.running:
            return

        self.score += dt
        self._invuln = max(0.0, self._invuln - dt)
        self._hit_flash = max(0.0, self._hit_flash - dt)

        # Move the avatar according to the held direction.
        self.avatar += self.move_dir * self.AVATAR_SPEED * dt
        self.avatar = max(0.0, min(self.manager.count - 1, self.avatar))

        speed = self._speed()

        # Spawn obstacles from a random end.
        self._spawn_timer -= dt
        if self._spawn_timer <= 0:
            self._spawn_timer = max(0.35, self.SPAWN_INTERVAL - self.elapsed * 0.01)
            direction = 1 if random.random() < 0.5 else -1
            start = -1.0 if direction == 1 else self.manager.count
            self.obstacles.append({
                "pos": start,
                "dir": direction,
                "speed": speed * random.uniform(0.8, 1.4),
            })

        # Move obstacles.
        for obs in self.obstacles:
            obs["pos"] += obs["dir"] * obs["speed"] * dt

        # Collision detection.
        if self._invuln <= 0:
            for obs in self.obstacles:
                if abs(obs["pos"] - self.avatar) < 0.6:
                    self._on_hit()
                    break

        # Remove obstacles that left the strip.
        self.obstacles = [
            o for o in self.obstacles if -2 < o["pos"] < self.manager.count + 1
        ]

    def handle_input(self, player_id, action):
        if not self.running:
            return
        if action == "left":
            self.move_dir = -1
        elif action == "right":
            self.move_dir = 1
        elif action == "stop":
            self.move_dir = 0

    def _on_hit(self):
        self.lives -= 1
        self._invuln = self.INVULN_TIME
        self._hit_flash = 1.0
        if self.lives <= 0:
            self._finish()

    def _finish(self):
        if self.players:
            self.winner = self.players[0].id
        self.results = {
            "survival_time": round(self.score, 1),
            "lives": max(0, self.lives),
        }
        if self.players:
            self.players[0].score = int(self.score * 10)
        self.end()

    def render(self, frame, dt):
        player_color = self.players[0].color if self.players else (0, 200, 255)

        # Obstacles (red/orange), blinking when close to the avatar.
        for obs in self.obstacles:
            idx = int(round(obs["pos"]))
            if 0 <= idx < frame.count:
                frame.set(idx, (230, 40, 40))

        # Avatar: bright, blinking while invulnerable.
        idx = int(round(self.avatar))
        if 0 <= idx < frame.count:
            if self._invuln > 0 and int(self._invuln * 8) % 2 == 0:
                frame.set(idx, (255, 255, 255))
            else:
                frame.set(idx, player_color)

        # Hit flash: wash the whole strip red.
        if self._hit_flash > 0:
            for i in range(frame.count):
                frame.blend(i, (255, 0, 0), self._hit_flash * 0.6)

    def render_tutorial(self, frame, step_index, elapsed, duration):
        center = (frame.count - 1) / 2.0
        avatar = center + (frame.count * 0.22) * math.sin(elapsed * 2.0)
        frame.set(int(round(avatar)), (0, 220, 255))
        if step_index == 0:
            for offset in range(min(5, frame.count)):
                frame.set(offset, (30, 80, 200) if offset % 2 == 0 else (8, 15, 35))
                frame.set(frame.count - 1 - offset, (30, 80, 200) if offset % 2 == 0 else (8, 15, 35))
        else:
            travel = max(1.0, frame.count - 1)
            obstacle = int((elapsed * 12.0) % travel)
            frame.set(obstacle, (255, 45, 35))
            frame.set(frame.count - 1 - obstacle, (255, 45, 35))

    def get_state(self):
        state = super().get_state()
        state.update({
            "lives": max(0, self.lives),
            "score": round(self.score, 1),
            "avatar": round(self.avatar, 1),
        })
        return state
