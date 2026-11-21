"""Shooter / LED Battle.

Cooperative shooter on a 1D strip. Each player owns a cannon on the left side
of the strip and fires projectiles rightward to destroy enemies that spawn on
the right and advance left. Enemies that reach the base damage shared health.
"""

import random

from led.colors import hsv_to_rgb, blend, dim

from arcade.games.base import BaseGame


class ShooterGame(BaseGame):
    name = "Shooter"
    slug = "shooter"
    description = "Fire at the incoming enemies before they reach your base!"
    min_players = 1
    max_players = None

    START_HEALTH = 10
    SPAWN_INTERVAL = 1.6
    BASE_SPEED = 5.0
    PROJECTILE_SPEED = 45.0
    GAME_TIME = 60.0
    tutorial_steps = (
        {"title": "Protect the base", "instruction": "Enemies approach from the far end of the strip.", "duration": 2.6},
        {"title": "Fire to destroy", "instruction": "Tap FIRE to launch a shot. Stop enemies reaching your base.", "duration": 2.6},
    )

    def __init__(self, manager):
        super().__init__(manager)
        self.health = self.START_HEALTH
        self.enemies = []
        self.projectiles = []
        self.explosions = []        # list of (index, ttl)
        self._spawn_timer = 1.0
        self._difficulty = 1.0
        self.cannons = {}           # player_id -> position

    def setup(self, players):
        super().setup(players)
        self._place_cannons()

    def _place_cannons(self):
        self.cannons = {}
        n = max(1, len(self.players))
        for i, p in enumerate(self.players):
            # Spread cannons across the left third of the strip.
            span = max(1, self.manager.count // 3)
            self.cannons[p.id] = int(span * i / n)

    def start(self):
        super().start()
        self.health = self.START_HEALTH
        self.enemies = []
        self.projectiles = []
        self.explosions = []
        self._spawn_timer = 1.0
        self._difficulty = 1.0

    def update(self, dt):
        super().update(dt)
        if not self.running:
            return

        self._difficulty = 1.0 + self.elapsed / 30.0

        # Spawn enemies at the right end, moving left.
        self._spawn_timer -= dt
        if self._spawn_timer <= 0:
            interval = max(0.5, self.SPAWN_INTERVAL / self._difficulty)
            self._spawn_timer = interval * random.uniform(0.7, 1.3)
            self.enemies.append({
                "pos": float(self.manager.count - 1),
                "speed": self.BASE_SPEED * self._difficulty * random.uniform(0.7, 1.4),
                "value": 1,
            })

        # Move enemies.
        for e in self.enemies:
            e["pos"] -= e["speed"] * dt

        # Move projectiles.
        for proj in self.projectiles:
            proj["pos"] += proj["dir"] * proj["speed"] * dt

        # Collisions.
        alive_enemies = []
        alive_projectiles = list(self.projectiles)
        for e in self.enemies:
            hit = False
            for proj in alive_projectiles:
                if proj["dir"] > 0 and abs(proj["pos"] - e["pos"]) < 0.7:
                    self.explosions.append((int(round(e["pos"])), 0.3))
                    owner = self.manager.players.get(proj["owner"])
                    if owner:
                        owner.score += e["value"]
                    alive_projectiles.remove(proj)
                    hit = True
                    break
            if hit:
                continue
            # Enemy reached the base (left end).
            if e["pos"] <= 0:
                self.health -= 1
                self.explosions.append((0, 0.5))
                if self.health <= 0:
                    self.health = 0
                    break
            else:
                alive_enemies.append(e)

        self.enemies = alive_enemies
        self.projectiles = alive_projectiles

        # Age explosions.
        self.explosions = [(i, ttl - dt) for i, ttl in self.explosions if ttl - dt > 0]

        if self.health <= 0 or self.elapsed >= self.GAME_TIME:
            self._finish()

    def handle_input(self, player_id, action):
        if not self.running:
            return
        if player_id not in self.cannons:
            self.cannons[player_id] = 0
        if action == "fire":
            self.projectiles.append({
                "pos": float(self.cannons[player_id]),
                "dir": 1,
                "speed": self.PROJECTILE_SPEED,
                "owner": player_id,
            })
        elif action == "left":
            self.cannons[player_id] = max(0, self.cannons[player_id] - 1)
        elif action == "right":
            self.cannons[player_id] = min(
                self.manager.count // 2, self.cannons[player_id] + 1)

    def _finish(self):
        self.winner = None
        if self.players:
            self.winner = max(self.players, key=lambda p: p.score).id
        self.results = {
            "health": max(0, self.health),
            "survived": self.elapsed >= self.GAME_TIME,
        }
        self.end()

    def render(self, frame, dt):
        # Enemies: red, brighter as they get closer to the base.
        for e in self.enemies:
            idx = int(round(e["pos"]))
            if 0 <= idx < frame.count:
                frame.set(idx, (200, 30, 30))

        # Projectiles: bright white/cyan dots.
        for proj in self.projectiles:
            idx = int(round(proj["pos"]))
            if 0 <= idx < frame.count:
                frame.set(idx, (180, 240, 255))

        # Cannons: player colours.
        for pid, pos in self.cannons.items():
            player = self.manager.players.get(pid)
            if player and 0 <= pos < frame.count:
                frame.set(pos, player.color)

        # Explosions: white flash.
        for idx, _ in self.explosions:
            if 0 <= idx < frame.count:
                frame.set(idx, (255, 255, 255))

        # Base health indicator on the first few LEDs.
        for i in range(min(3, frame.count)):
            if i < int(self.health * 3 / self.START_HEALTH):
                frame.set(i, (0, 200, 0))

    def render_tutorial(self, frame, step_index, elapsed, duration):
        base = 1
        enemy = max(base + 5, frame.count - 1 - int(elapsed * 5.0) % max(1, frame.count - 5))
        frame.set(base, (0, 220, 100))
        frame.set(enemy, (255, 40, 35))
        if step_index == 1:
            shot = min(enemy, base + int(elapsed * self.PROJECTILE_SPEED))
            frame.set(shot, (220, 250, 255))
            if shot >= enemy - 1:
                frame.set(enemy, (255, 255, 255))

    def get_state(self):
        state = super().get_state()
        state.update({
            "health": max(0, self.health),
            "enemies": len(self.enemies),
            "difficulty": round(self._difficulty, 2),
        })
        return state
