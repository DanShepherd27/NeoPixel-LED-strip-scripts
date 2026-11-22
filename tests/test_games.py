"""Game and lobby rules: python -m unittest discover tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcade.games.shooter import ShooterGame  # noqa: E402
from arcade.manager import ArcadeManager  # noqa: E402
from arcade.state import ArcadeState  # noqa: E402
from led.frame import Frame  # noqa: E402


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


def run(manager, seconds):
    frame = Frame(manager.count)
    for _ in range(int(seconds * 60)):
        manager.render(frame, 1 / 60)


class LobbyFlowTests(unittest.TestCase):
    def setUp(self):
        self.manager = ArcadeManager(count=60)

    def to_tutorial(self, slug, *names):
        players = [self.manager.join_player(name) for name in names]
        self.manager.select_game(slug)
        for player in players:
            self.manager.set_ready(player.id, True)
        self.manager.start_game()
        return players

    def test_solo_game_starts_without_ready_and_skips_ready_after_tutorial(self):
        solo = self.manager.join_player("Solo")
        self.manager.select_game("shooter")
        self.manager.start_game()
        self.assertEqual(self.manager.state, ArcadeState.TUTORIAL)
        self.manager.tutorial_next(solo.id)
        self.manager.tutorial_next(solo.id)
        self.assertEqual(self.manager.state, ArcadeState.COUNTDOWN)
        self.assertFalse(self.manager.get_state()["ready_required"])

    def test_multiplayer_still_needs_everyone_ready(self):
        a = self.manager.join_player("A")
        b = self.manager.join_player("B")
        self.manager.select_game("shooter")
        self.manager.set_ready(a.id, True)
        self.manager.start_game()
        self.assertEqual(self.manager.state, ArcadeState.LOBBY)
        self.manager.set_ready(b.id, True)
        self.manager.start_game()
        self.assertEqual(self.manager.state, ArcadeState.TUTORIAL)

    def test_tutorial_waits_for_next(self):
        (a, b) = self.to_tutorial("shooter", "A", "B")
        run(self.manager, 30)
        self.assertEqual(self.manager.get_state()["tutorial"]["index"], 1)
        self.manager.tutorial_next(a.id)
        self.assertEqual(self.manager.get_state()["tutorial"]["index"], 2)

    def test_extra_players_queue_first_come_first_served(self):
        a, b, c, d = (self.manager.join_player(name) for name in "ABCD")
        self.manager.select_game("pong")
        snapshot = {p["id"]: p for p in self.manager.get_state()["players"]}
        self.assertFalse(snapshot[a.id]["queued"] or snapshot[b.id]["queued"])
        self.assertEqual((snapshot[c.id]["queue_position"], snapshot[d.id]["queue_position"]), (1, 2))
        self.manager.set_ready(c.id, True)            # queued players cannot ready up
        self.assertFalse(c.ready)
        for player in (a, b):
            self.manager.set_ready(player.id, True)
        self.manager.start_game()
        self.assertEqual([p.id for p in self.manager.game.players], [a.id, b.id])

    def test_queue_gets_the_next_game_and_players_rotate_to_the_back(self):
        a, b, c = (self.manager.join_player(name) for name in "ABC")
        self.manager.select_game("pong")
        for player in (a, b):
            self.manager.set_ready(player.id, True)
        self.manager.start_game()
        self.manager._enter_results()
        self.manager.results_timer = 0.0
        run(self.manager, 0.1)
        self.assertEqual(self.manager.state, ArcadeState.LOBBY)
        self.manager.select_game("pong")
        queued = {p["id"] for p in self.manager.get_state()["players"] if p["queued"]}
        self.assertEqual(queued, {b.id})
        self.assertFalse(c.id in queued)

    def test_silent_players_stop_blocking_the_lobby(self):
        a = self.manager.join_player("A")
        b = self.manager.join_player("B")
        self.manager.select_game("shooter")
        self.manager.set_ready(a.id, True)
        b.last_seen -= 60
        run(self.manager, 1.5)
        self.assertFalse(b.connected)
        self.manager.start_game()
        self.assertEqual(self.manager.state, ArcadeState.TUTORIAL)


class VoteKickTests(unittest.TestCase):
    def setUp(self):
        self.manager = ArcadeManager(count=60)
        self.a, self.b, self.c = (self.manager.join_player(name) for name in "ABC")

    def test_a_majority_of_the_others_removes_the_player(self):
        self.assertIsNone(self.manager.vote_kick(self.a.id, self.c.id))
        self.assertIsNotNone(self.manager.players.get(self.c.id))
        removed = self.manager.vote_kick(self.b.id, self.c.id)
        self.assertEqual(removed.id, self.c.id)
        self.assertIsNone(self.manager.players.get(self.c.id))
        self.assertIn(self.c.id, self.manager.get_state()["kicked"])

    def test_votes_can_be_withdrawn_and_do_not_count_for_oneself(self):
        self.manager.vote_kick(self.a.id, self.c.id)
        self.manager.vote_kick(self.a.id, self.c.id)                      # withdraw
        self.assertIsNone(self.manager.vote_kick(self.b.id, self.c.id))
        self.assertIsNone(self.manager.vote_kick(self.c.id, self.c.id))
        self.assertEqual(self.manager.players.get(self.c.id).kick_votes, {self.b.id})

    def test_kicking_the_only_player_of_a_running_game_hands_over_to_the_queue(self):
        self.manager.select_game("dodge")                                  # one seat: A plays
        self.manager.start_game()
        self.assertEqual(self.manager.state, ArcadeState.TUTORIAL)
        self.manager.vote_kick(self.b.id, self.a.id)
        self.manager.vote_kick(self.c.id, self.a.id)
        self.assertIsNone(self.manager.players.get(self.a.id))
        self.assertEqual(self.manager.state, ArcadeState.LOBBY)
        self.assertEqual(self.manager.players.count(), 2)

    def test_voting_is_only_for_connected_voters(self):
        self.b.connected = False
        self.assertIsNone(self.manager.vote_kick(self.b.id, self.c.id))
        self.assertEqual(self.manager.players.get(self.c.id).kick_votes, set())


if __name__ == "__main__":
    unittest.main()
