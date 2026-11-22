"""Game and lobby rules: python -m unittest discover tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcade.games.shooter import ShooterGame  # noqa: E402
from arcade.manager import ArcadeManager  # noqa: E402


class ShooterTests(unittest.TestCase):
    def setUp(self):
        self.manager = ArcadeManager(count=60)
        self.a = self.manager.join_player("A")
        self.b = self.manager.join_player("B")
        self.game = ShooterGame(self.manager)
        self.game.setup([self.a, self.b])
        self.game.start()

    def test_fast_shot_cannot_tunnel_through_an_enemy(self):
        self.game.enemies = [{"pos": 30.0, "speed": 5.0, "value": 1}]
        self.game.projectiles = [{"pos": 25.0, "speed": 45.0, "owner": self.a.id}]
        self.game._advance(0.5)
        self.assertEqual(self.a.score, 1)
        self.assertEqual(self.game.enemies, [])

    def test_enemy_reaching_the_base_costs_health(self):
        self.game.enemies = [{"pos": self.game.base_edge + 0.5, "speed": 5.0, "value": 1}]
        self.game._advance(0.5)
        self.assertEqual(self.game.health, self.game.START_HEALTH - 1)

    def test_cannons_stay_inside_the_base_zone(self):
        for _ in range(100):
            self.game.handle_input(self.a.id, "right")
        self.assertEqual(self.game.cannons[self.a.id], self.game.base_edge)
        for _ in range(100):
            self.game.handle_input(self.a.id, "left")
        self.assertEqual(self.game.cannons[self.a.id], 1)

    def test_only_participants_can_shoot_and_fire_is_rate_limited(self):
        self.game.handle_input("spectator", "fire")
        self.assertEqual(self.game.projectiles, [])
        self.game.handle_input(self.a.id, "fire")
        self.game.handle_input(self.a.id, "fire")
        self.assertEqual(len(self.game.projectiles), 1)


if __name__ == "__main__":
    unittest.main()
