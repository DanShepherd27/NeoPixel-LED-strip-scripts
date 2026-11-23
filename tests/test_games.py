"""Game and lobby rules: python -m unittest discover tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcade.games.pong import PongGame  # noqa: E402
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


class PongMachineTests(unittest.TestCase):
    def setUp(self):
        self.manager = ArcadeManager(count=60)
        self.human = self.manager.join_player("A")

    def solo_game(self):
        game = PongGame(self.manager)
        game.setup([self.human])
        game.start()
        game.phase = game.PLAY
        return game

    def test_solo_player_can_start_without_readying(self):
        self.manager.select_game("pong")
        self.manager.start_game()
        self.assertEqual(self.manager.state, ArcadeState.TUTORIAL)
        self.assertTrue(self.manager.get_state()["game"]["vs_machine"])

    def test_two_players_play_each_other(self):
        other = self.manager.join_player("B")
        game = PongGame(self.manager)
        game.setup([self.human, other])
        game.start()
        self.assertFalse(game.vs_machine)
        self.assertEqual(set(game.points), {self.human.id, other.id})

    def test_machine_returns_the_ball_after_a_reaction_delay(self):
        game = self.solo_game()
        game.MACHINE_TIMING_ERROR = 0.0
        game.ball, game.direction, game.speed = 50.0, 1, game.LEVEL_START_SPEEDS[0]
        for _ in range(40):
            game.update(0.025)
        self.assertEqual(game.direction, -1)
        self.assertEqual(game.last_hit_by, game.MACHINE_ID)

    def test_machine_misses_and_the_player_scores(self):
        game = self.solo_game()
        game.MACHINE_TIMING_ERROR = 0.0
        game._plan_machine_swing = lambda: 0.1          # swings long before the ball is in reach
        game.ball, game.direction = 40.0, 1
        for _ in range(120):
            game.update(0.025)
            if game.points[self.human.id]:
                break
        self.assertEqual(game.points[self.human.id], 1)

    def test_machine_scores_when_the_player_misses_and_can_win(self):
        game = self.solo_game()
        game.wins[game.MACHINE_ID] = game.LEVELS_TO_WIN - 1
        game.points[game.MACHINE_ID] = game.LEVEL_POINTS - 1
        game.ball, game.direction = 2.0, -1
        game.update(0.5)
        self.assertEqual(game.winner, game.MACHINE_ID)
        self.assertTrue(game.finished)
        self.assertEqual(game.results["winner_name"], "The machine")

    def test_player_cannot_hit_for_the_machine_and_hits_own_end(self):
        game = self.solo_game()
        game.ball, game.direction = 58.0, 1
        game.handle_input(self.human.id, "hit")
        self.assertEqual(game.direction, 1)          # the human guards the left end only
        game.ball, game.direction = 2.0, -1
        game.handle_input(self.human.id, "hit")
        self.assertEqual(game.direction, 1)

    def test_machine_win_is_named_in_the_results_state(self):
        self.manager.select_game("pong")
        self.manager.start_game()
        game = self.manager.game
        game.start()
        game.phase = game.PLAY
        game.wins[game.MACHINE_ID] = game.LEVELS_TO_WIN - 1
        game.points[game.MACHINE_ID] = game.LEVEL_POINTS - 1
        game.ball, game.direction = 2.0, -1
        game.update(0.5)
        self.assertEqual(self.manager.get_state()["game"]["winner_name"], "The machine")

    def test_machine_never_reacts_faster_than_its_reaction_time(self):
        game = self.solo_game()
        game.MACHINE_TIMING_ERROR = 0.0
        game.ball, game.direction, game.speed = 55.5, 1, 20.0   # inside the zone, point still live
        game.update(0.1)
        self.assertEqual(game.direction, 1)                      # 0.1 s < 0.25 s reaction time
        game.update(0.2)                                         # 0.3 s in: it may swing now
        self.assertIn(game.direction, (1, -1))
        self.assertTrue(game._machine_swung or game.points[self.human.id] == 1)


class PongLevelTests(unittest.TestCase):
    def setUp(self):
        self.manager = ArcadeManager(count=60)
        self.a = self.manager.join_player("A")
        self.b = self.manager.join_player("B")
        self.game = PongGame(self.manager)
        self.game.setup([self.a, self.b])
        self.game.start()
        self.game.phase = self.game.PLAY

    def score(self, scorer):
        """Let the ball leave the strip at the end opposite the scorer."""
        left = scorer == self.a.id
        self.game.phase = self.game.PLAY
        self.game.ball = 59.5 if left else 0.5
        self.game.direction = 1 if left else -1
        self.game.update(0.1)

    def test_each_hit_speeds_the_ball_up_and_a_point_resets_the_rally(self):
        self.game.ball, self.game.direction = 2.0, -1
        before = self.game.speed
        self.game.handle_input(self.a.id, "hit")
        self.assertGreater(self.game.speed, before)
        self.score(self.a.id)
        self.assertEqual(self.game.speed, self.game.LEVEL_START_SPEEDS[0])
        self.assertEqual(self.game.phase, self.game.SERVE)

    def test_clearing_a_level_pauses_until_every_player_starts_the_next(self):
        for _ in range(self.game.LEVEL_POINTS):
            self.score(self.a.id)
        self.assertEqual(self.game.phase, self.game.BREAK)
        self.assertEqual(self.game.wins[self.a.id], 1)
        self.game.handle_input("spectator", "next_level")
        self.game.handle_input(self.a.id, "hit")
        self.game.update(5.0)
        self.assertEqual(self.game.phase, self.game.BREAK)
        self.game.handle_input(self.a.id, "next_level")
        self.game.update(5.0)
        self.assertEqual(self.game.phase, self.game.BREAK)          # b has not pressed start
        self.game.handle_input(self.b.id, "next_level")
        self.game.update(0.1)
        self.assertEqual((self.game.level, self.game.phase), (2, self.game.SERVE))
        self.assertEqual(self.game.speed, self.game.LEVEL_START_SPEEDS[1])
        self.assertEqual(self.game.points[self.a.id], 0)

    def test_an_absent_player_does_not_hold_up_the_next_level(self):
        for _ in range(self.game.LEVEL_POINTS):
            self.score(self.a.id)
        self.b.connected = False
        self.game.handle_input(self.a.id, "next_level")
        self.game.update(0.1)
        self.assertEqual(self.game.level, 2)

    def test_winning_enough_levels_ends_the_match(self):
        for level in range(self.game.LEVELS_TO_WIN):
            for _ in range(self.game.LEVEL_POINTS):
                self.score(self.a.id)
            if level + 1 < self.game.LEVELS_TO_WIN:
                self.game.handle_input(self.a.id, "next_level")
                self.game.handle_input(self.b.id, "next_level")
                self.game.update(0.1)
        self.assertTrue(self.game.finished)
        self.assertEqual(self.game.winner, self.a.id)

    def test_each_end_is_lit_in_its_guards_color(self):
        frame = Frame(60)
        self.game.render(frame, 0.0)
        self.assertEqual(frame.pixels[0], tuple(self.a.color))
        self.assertEqual(frame.pixels[59], tuple(self.b.color))


class AdminOffsetTests(unittest.TestCase):
    def test_games_draw_only_on_the_visible_leds(self):
        manager = ArcadeManager(count=60)
        manager.hidden_offsets = lambda: (10, 6)
        self.assertEqual(manager.play_count, 44)
        player = manager.join_player("A")
        manager.select_game("pong")
        manager.start_game()
        manager._start_game()
        frame = Frame(60)
        manager.render(frame, 1 / 40)
        lit = [index for index, pixel in enumerate(frame.pixels) if pixel != (0, 0, 0)]
        self.assertEqual(frame.pixels[10], tuple(player.color))      # first visible LED is the player's end
        self.assertEqual(frame.pixels[53], PongGame.MACHINE_COLOR)   # last visible LED is the machine's
        self.assertTrue(all(10 <= index < 54 for index in lit))
        self.assertEqual(manager.game._last_pixel(), 43)


if __name__ == "__main__":
    unittest.main()
