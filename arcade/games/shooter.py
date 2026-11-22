"""Shooter / LED Battle.

Cooperative shooter on a 1D strip. Each player owns a cannon inside the base
zone at the strip's start and fires rightward at enemies that spawn at the far
end and advance. Enemies that reach the base's edge damage shared health.
"""

import math
import random

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
    FIRE_COOLDOWN = 0.15        # seconds between shots from one player
    GAME_TIME = 60.0
    tutorial_steps = (
        {"title": "Protect the base", "instruction": "Red enemies march toward your green base. Don't let them reach it.", "duration": 4.5},
        {"title": "Move and fire", "instruction": "Use the arrows to slide your cannon and tap FIRE to shoot.", "duration": 4.5},
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
        self._last_shot = {}        # player_id -> game time of the last shot

    # The base is the zone at the strip's start; cannons live inside it and
    # enemies that reach its far edge hit the base.
    @property
    def base_edge(self):
        return max(3, self.manager.count // 6)

    def setup(self, players):
        super().setup(players)
        self._place_cannons()

    def _place_cannons(self):
        self.cannons = {}
        edge = self.base_edge
        n = max(1, len(self.players))
        for i, p in enumerate(self.players):
            self.cannons[p.id] = 1 + int((edge - 1) * (i + 0.5) / n)

    def start(self):
        super().start()
        self.health = self.START_HEALTH
        self.enemies = []
        self.projectiles = []
        self.explosions = []
        self._spawn_timer = 1.0
        self._difficulty = 1.0
        self._last_shot = {}
        for p in self.players:
            p.score = 0
        self._place_cannons()

    def update(self, dt):
        super().update(dt)
        if not self.running:
            return

        self._difficulty = 1.0 + self.elapsed / 30.0

        self._spawn_timer -= dt
        if self._spawn_timer <= 0:
            interval = max(0.5, self.SPAWN_INTERVAL / self._difficulty)
            self._spawn_timer = interval * random.uniform(0.7, 1.3)
            self.enemies.append({
                "pos": float(self.manager.count - 1),
                "speed": self.BASE_SPEED * self._difficulty * random.uniform(0.7, 1.4),
                "value": 1,
            })

        self._advance(dt)
        self.explosions = [(i, ttl - dt) for i, ttl in self.explosions if ttl - dt > 0]

        if self.health <= 0 or self.elapsed >= self.GAME_TIME:
            self._finish()

    def _advance(self, dt):
        """Move everything and resolve hits with swept collision.

        Shots are tested against the whole distance they and the enemy
        covered this step, so a slow frame cannot let a shot tunnel through.
        """
        previous_enemy = [e["pos"] for e in self.enemies]
        for e in self.enemies:
            e["pos"] -= e["speed"] * dt
        previous_shot = [proj["pos"] for proj in self.projectiles]
        for proj in self.projectiles:
            proj["pos"] += proj["speed"] * dt

        spent = set()
        survivors = []
        for e, e_before in zip(self.enemies, previous_enemy):
            hit_by = None
            for index, (proj, p_before) in enumerate(zip(self.projectiles, previous_shot)):
                if index in spent:
                    continue
                # Shot and enemy approach each other: they meet if their order swapped.
                if p_before <= e_before + 0.5 and proj["pos"] >= e["pos"] - 0.5:
                    hit_by = index
                    break
            if hit_by is not None:
                spent.add(hit_by)
                self.explosions.append((int(round(e["pos"])), 0.3))
                owner = self.manager.players.get(self.projectiles[hit_by]["owner"])
                if owner:
                    owner.score += e["value"]
            elif e["pos"] <= self.base_edge:
                self.health -= 1
                self.explosions.append((int(round(self.base_edge)), 0.5))
            else:
                survivors.append(e)
        self.enemies = survivors
        self.projectiles = [
            proj for index, proj in enumerate(self.projectiles)
            if index not in spent and proj["pos"] < self.manager.count
        ]

    def handle_input(self, player_id, action):
        # Only the players who started this game control a cannon.
        if not self.running or player_id not in self.cannons:
            return
        if action == "fire":
            if self.elapsed - self._last_shot.get(player_id, -1.0) < self.FIRE_COOLDOWN:
                return
            self._last_shot[player_id] = self.elapsed
            self.projectiles.append({
                "pos": float(self.cannons[player_id]),
                "speed": self.PROJECTILE_SPEED,
                "owner": player_id,
            })
        elif action == "left":
            self.cannons[player_id] = max(1, self.cannons[player_id] - 1)
        elif action == "right":
            self.cannons[player_id] = min(self.base_edge, self.cannons[player_id] + 1)

    def _finish(self):
        self.winner = None
        if self.players:
            self.winner = max(self.players, key=lambda p: p.score).id
        self.results = {
            "health": max(0, self.health),
            "survived": self.health > 0,
        }
        self.end()

    def render(self, frame, dt):
        self._draw_base(frame)

        for e in self.enemies:
            idx = int(round(e["pos"]))
            if 0 <= idx < frame.count:
                frame.set(idx, (200, 30, 30))

        for proj in self.projectiles:
            idx = int(round(proj["pos"]))
            if 0 <= idx < frame.count:
                frame.set(idx, (180, 240, 255))

        for pid, pos in self.cannons.items():
            player = self.manager.players.get(pid)
            if player and 0 <= pos < frame.count:
                frame.set(pos, player.color)

        for idx, _ in self.explosions:
            if 0 <= idx < frame.count:
                frame.set(idx, (255, 255, 255))

    def _draw_base(self, frame):
        """Faint green base zone; the bright part shrinks with remaining health."""
        edge = self.base_edge
        lit = int(round(edge * max(0, self.health) / self.START_HEALTH))
        for i in range(min(edge + 1, frame.count)):
            frame.set(i, (0, 150, 0) if i < lit else (0, 25, 0))

    def render_tutorial(self, frame, step_index, elapsed, duration):
        self._draw_base(frame)
        edge = self.base_edge
        phase = (elapsed % duration) / duration
        enemy = frame.count - 1 - phase * (frame.count - 1 - edge - 8)
        if step_index == 0:
            frame.set(int(enemy), (255, 40, 35))
            return
        # Step 2: the cannon slides, fires, and the shot removes the enemy.
        cannon = 1 + int((edge - 1) * (0.5 + 0.5 * math.sin(phase * 2 * math.pi)))
        cycle = (phase * 3.0) % 1.0
        enemy_pos = frame.count - 1 - cycle * (frame.count - 1 - edge - 8)
        shot = cannon + cycle * 1.6 * (frame.count - cannon)
        if shot < enemy_pos:
            frame.set(int(enemy_pos), (255, 40, 35))
            frame.set(int(shot), (220, 250, 255))
        elif cycle < 0.75:
            frame.set(int(min(frame.count - 1, enemy_pos)), (255, 255, 255))
        frame.set(cannon, (0, 220, 255))

    def get_state(self):
        state = super().get_state()
        state.update({
            "health": max(0, self.health),
            "enemies": len(self.enemies),
            "difficulty": round(self._difficulty, 2),
        })
        return state
