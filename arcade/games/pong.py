"""Strip Pong — a one-dimensional Pong game for one or two players.

A ball travels along the strip. Each player guards one end, lit in their own
color, and must hit the ball while it is inside that end's zone. Every hit
reverses the ball and speeds it up (a longer trail and a higher beep show it).
A miss gives the opponent a point; the first to ``LEVEL_POINTS`` clears the
level. Each level starts faster, and the game pauses between levels until every
player presses start on their phone. Win ``LEVELS_TO_WIN`` levels to win. A lone
player faces the machine, which guards the far end with a human-like reaction
delay and a chance to miss that grows with the ball speed.
"""

import math
import random

from led.colors import blend, dim

from arcade.games.base import BaseGame


class PongGame(BaseGame):
    name = "Pong"
    slug = "pong"
    description = "Hit the ball before it reaches your end! Three levels, each faster."
    min_players = 1
    max_players = 2

    LEVELS = 3
    LEVELS_TO_WIN = 2
    LEVEL_POINTS = 3                          # points that clear a level
    LEVEL_START_SPEEDS = (18.0, 26.0, 34.0)   # LEDs/sec at the start of each level
    SPEEDUP = 3.5                             # LEDs/sec added per hit
    MAX_SPEED = 64.0
    HIT_ZONE = 4                              # LEDs from each end considered the hit zone
    SERVE_SECONDS = 1.0
    HIT_FLASH_SECONDS = 0.25
    SERVE, PLAY, BREAK = "serve", "play", "break"

    MACHINE_ID = "machine"
    MACHINE_NAME = "The machine"
    MACHINE_COLOR = (0, 200, 255)
    MACHINE_MIN_REACTION = 0.25       # seconds: never swings sooner than this after the ball is sent
    MACHINE_TIMING_ERROR = 0.05       # seconds (standard deviation) off the middle of the zone
    tutorial_steps = (
        {"title": "Your end is your color", "instruction": "One end of the strip glows in YOUR color: that end is yours. Playing alone? The machine guards the cyan end.", "duration": 4.5},
        {"title": "Tap HIT in the zone", "instruction": "When the ball reaches the glowing zone at your end, tap HIT to send it back.", "duration": 4.5},
        {"title": "Faster every level", "instruction": "Each hit speeds the ball up: longer trail, higher beep. Win 3 points to clear a level, win 2 of 3 levels to win. Between levels your phone waits until you start the next one.", "duration": 5.5},
    )

    def __init__(self, manager):
        super().__init__(manager)
        self.ball = 0.0
        self.direction = 1
        self.speed = self.LEVEL_START_SPEEDS[0]
        self.level = 1
        self.phase = self.SERVE
        self.points = {}          # points in the current level
        self.wins = {}            # levels won
        self.total_points = {}
        self.last_hit_by = None
        self.level_winner = None
        self._serve_left = 0.0
        self._break_ready = set()
        self._flash = 0.0
        self._flash_color = (255, 255, 255)
        self._hit_flash = {"left": 0.0, "right": 0.0}
        self._machine_swing_in = None   # seconds until the machine swings at the ball sent its way
        self._machine_swung = False

    # -- seats ---------------------------------------------------------------
    @property
    def vs_machine(self):
        return len(self.players) == 1

    def _left_id(self):
        return self.players[0].id if self.players else None

    def _right_id(self):
        """Who guards the other end: the second player, or the machine when playing alone."""
        if len(self.players) >= 2:
            return self.players[1].id
        return self.MACHINE_ID if self.vs_machine else None

    def _seat_ids(self):
        return [pid for pid in (self._left_id(), self._right_id()) if pid is not None]

    def _color_of(self, player_id):
        if player_id == self.MACHINE_ID:
            return self.MACHINE_COLOR
        for player in self.players:
            if player.id == player_id:
                return tuple(player.color)
        return (255, 255, 255)

    def _name_of(self, player_id):
        if player_id == self.MACHINE_ID:
            return self.MACHINE_NAME
        for player in self.players:
            if player.id == player_id:
                return player.name
        return ""

    def _end_colors(self):
        return self._color_of(self._left_id()), self._color_of(self._right_id())

    # -- geometry ------------------------------------------------------------
    def _last_pixel(self):
        return self.manager.play_count - 1

    def _zone(self, count=None):
        count = self.manager.play_count if count is None else count
        return max(1, min(self.HIT_ZONE, count // 4))

    def _level_speed(self):
        return self.LEVEL_START_SPEEDS[min(self.level, self.LEVELS) - 1]

    # -- lifecycle -----------------------------------------------------------
    def setup(self, players):
        super().setup(players)
        self.players = players[:2]
        self._reset_scores()

    def _reset_scores(self):
        ids = self._seat_ids()
        self.points = {pid: 0 for pid in ids}
        self.wins = {pid: 0 for pid in ids}
        self.total_points = {pid: 0 for pid in ids}

    def start(self):
        super().start()
        self.level = 1
        self.level_winner = None
        self._reset_scores()
        self._begin_serve(random_direction=True)

    def _begin_serve(self, random_direction=False):
        self.ball = self._last_pixel() / 2.0
        if random_direction:
            self.direction = random.choice([-1, 1])
        self.speed = self._level_speed()
        self.last_hit_by = None
        self._machine_swing_in = None
        self._machine_swung = False
        self.phase = self.SERVE
        self._serve_left = self.SERVE_SECONDS

    # -- per-frame update ----------------------------------------------------
    def update(self, dt):
        super().update(dt)
        if not self.running:
            return

        self._flash = max(0.0, self._flash - dt)
        for side in self._hit_flash:
            self._hit_flash[side] = max(0.0, self._hit_flash[side] - dt)

        if self.phase == self.BREAK:
            self._maybe_start_next_level()
            return
        if self.phase == self.SERVE:
            self._serve_left -= dt
            if self._serve_left <= 0:
                self.phase = self.PLAY
                self.manager.sound("serve")
            return

        self._update_machine(dt)
        self.ball += self.direction * self.speed * dt

        # The ball left the strip: the guard of the opposite end scores.
        if self.ball <= 0:
            self._score(self._right_id())
        elif self.ball >= self._last_pixel():
            self._score(self._left_id())

    def _score(self, scorer):
        if scorer is None:
            return
        self.points[scorer] += 1
        self.total_points[scorer] += 1
        self._flash = 0.6
        self._flash_color = self._color_of(scorer)
        self.manager.sound("point")
        if self.points[scorer] >= self.LEVEL_POINTS:
            self._finish_level(scorer)
        else:
            self._begin_serve()      # the ball keeps heading to whoever just conceded

    def _finish_level(self, winner):
        self.wins[winner] += 1
        self.level_winner = winner
        if self.wins[winner] >= self.LEVELS_TO_WIN or self.level >= self.LEVELS:
            self._finish_match(winner)
            return
        self.phase = self.BREAK
        self._break_ready = set()
        self.ball = self._last_pixel() / 2.0
        self.manager.sound("level_clear")

    def _finish_match(self, winner):
        self.winner = winner
        self.results = {"scores": dict(self.wins), "points": dict(self.total_points)}
        if winner == self.MACHINE_ID:
            self.results["winner_name"] = self.MACHINE_NAME
            self.results["winner_color"] = list(self.MACHINE_COLOR)
        for player in self.players:
            player.score = self.wins.get(player.id, 0)
        self.end()

    # -- level breaks --------------------------------------------------------
    def _maybe_start_next_level(self):
        """Resume once every connected player has pressed start for the next level."""
        waiting = [p for p in self.players if p.connected and p.id not in self._break_ready]
        if self._break_ready and not waiting:
            self.level += 1
            self.points = {pid: 0 for pid in self._seat_ids()}
            self._begin_serve(random_direction=True)
            self.manager.sound("level_start")

    # -- machine opponent ----------------------------------------------------
    def _plan_machine_swing(self):
        """Aim for the middle of the zone; timing error costs more as the ball gets faster."""
        zone = self._zone()
        middle = self._last_pixel() - zone + zone / 2.0
        planned = (middle - self.ball) / self.speed + random.gauss(0.0, self.MACHINE_TIMING_ERROR)
        return max(self.MACHINE_MIN_REACTION, planned)

    def _update_machine(self, dt):
        """Swing once per ball sent towards the machine; it hits only if the ball is in the zone."""
        if not self.vs_machine:
            return
        if self.direction != 1:
            self._machine_swing_in = None
            self._machine_swung = False
            return
        if self._machine_swung:
            return
        if self._machine_swing_in is None:
            self._machine_swing_in = self._plan_machine_swing()
        self._machine_swing_in -= dt
        if self._machine_swing_in > 0:
            return
        self._machine_swung = True
        if self.ball >= self._last_pixel() - self._zone():
            self.direction = -1
            self._speed_up(self.MACHINE_ID)

    # -- input ---------------------------------------------------------------
    def handle_input(self, player_id, action):
        if not self.running:
            return
        if action == "next_level":
            if self.phase == self.BREAK and any(p.id == player_id for p in self.players):
                self._break_ready.add(player_id)
            return
        if action != "hit" or self.phase != self.PLAY or not self.players:
            return

        if player_id == self._left_id():
            # The first player can only hit a ball moving towards their end, within its zone.
            if self.direction == -1 and self.ball <= self._zone():
                self.direction = 1
                self._speed_up(player_id)
        elif player_id == self._right_id() and not self.vs_machine:
            if self.direction == 1 and self.ball >= self._last_pixel() - self._zone():
                self.direction = -1
                self._speed_up(player_id)

    def _speed_up(self, player_id):
        self.speed = min(self.MAX_SPEED, self.speed + self.SPEEDUP)
        self.last_hit_by = player_id
        self._hit_flash["left" if player_id == self._left_id() else "right"] = self.HIT_FLASH_SECONDS
        rally_step = int((self.speed - self._level_speed()) / self.SPEEDUP)
        self.manager.sound("hit%d" % max(0, min(7, rally_step)))

    # -- rendering -----------------------------------------------------------
    def _draw_end(self, frame, zone, from_start, color, intensity, glow):
        """One end's hit zone in its guard's color; ``glow`` (0-1) lights it up after a hit."""
        for step in range(zone):
            index = step if from_start else frame.count - 1 - step
            base = 1.0 if step == 0 else 0.3
            frame.set(index, blend(dim(color, base * intensity), color, glow))

    def _draw_ends(self, frame, intensity=1.0):
        zone = self._zone(frame.count)
        left_color, right_color = self._end_colors()
        flash = self.HIT_FLASH_SECONDS
        self._draw_end(frame, zone, True, left_color, intensity, self._hit_flash["left"] / flash)
        self._draw_end(frame, zone, False, right_color, intensity, self._hit_flash["right"] / flash)

    def _draw_ball(self, frame, position, direction, speed, brightness=1.0):
        head = int(round(position))
        tail = min(8, 1 + int(speed / 9.0))
        for step in range(tail, 0, -1):
            fade = 0.45 * (1.0 - step / (tail + 1.0))
            frame.set(head - direction * step, dim((255, 255, 255), fade * brightness))
        frame.set(head, dim((255, 255, 255), brightness))

    def render(self, frame, dt):
        if self.phase == self.BREAK:
            self._render_break(frame)
            return
        self._draw_ends(frame)
        if self.phase == self.SERVE:
            blink = int(self._serve_left * 8) % 2 == 0
            self._draw_ball(frame, self.ball, 0, 0.0, 1.0 if blink else 0.15)
        else:
            self._draw_ball(frame, self.ball, self.direction, self.speed)
        if self._flash > 0:
            # A point: the whole strip washes in the scorer's color.
            for index in range(frame.count):
                frame.blend(index, self._flash_color, self._flash * 0.7)

    def _render_break(self, frame):
        """Between levels: ends show who pressed start; blocks in the middle count the next level."""
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 6.0)
        zone = self._zone(frame.count)
        left_color, right_color = self._end_colors()
        for from_start, pid, color in ((True, self._left_id(), left_color),
                                       (False, self._right_id(), right_color)):
            ready = pid == self.MACHINE_ID or pid in self._break_ready
            self._draw_end(frame, zone, from_start, color, 1.0 if ready else 0.25 + 0.75 * pulse, 0.0)
        next_level = min(self.level + 1, self.LEVELS)
        middle = (frame.count - 1) / 2.0
        for block in range(next_level):
            offset = (block - (next_level - 1) / 2.0) * 5
            for pixel in range(3):
                frame.set(int(round(middle + offset)) + pixel - 1, dim((255, 180, 0), 0.3 + 0.7 * pulse))

    def render_tutorial(self, frame, step_index, elapsed, duration):
        self._draw_ends(frame, 0.55 + 0.45 * math.sin(elapsed * 4.0) ** 2 if step_index == 0 else 1.0)
        if step_index == 0:
            return
        span = max(1, frame.count - 1)
        if step_index == 1:
            travelled = elapsed * 0.45
        else:
            travelled = 0.4 * elapsed + 0.45 * elapsed * elapsed / duration     # keeps accelerating
        phase = travelled % 2.0
        rightwards = phase <= 1.0
        position = (phase if rightwards else 2.0 - phase) * span
        self._draw_ball(frame, position, 1 if rightwards else -1, 20.0 if step_index == 1 else 18.0 + 6.0 * elapsed)

    # -- web snapshot --------------------------------------------------------
    def get_state(self):
        state = super().get_state()
        base = self.LEVEL_START_SPEEDS[0]
        seats = []
        for index, pid in enumerate(self._seat_ids()):
            seats.append({
                "id": pid,
                "name": self._name_of(pid),
                "color": list(self._color_of(pid)),
                "side": "left" if index == 0 else "right",
                "points": self.points.get(pid, 0),
                "wins": self.wins.get(pid, 0),
            })
        state.update({
            "vs_machine": self.vs_machine,
            "phase": self.phase,
            "level": self.level,
            "levels": self.LEVELS,
            "level_points": self.LEVEL_POINTS,
            "levels_to_win": self.LEVELS_TO_WIN,
            "next_level": min(self.level + 1, self.LEVELS),
            "level_speed": self._level_speed(),
            "next_level_speed": self.LEVEL_START_SPEEDS[min(self.level, self.LEVELS - 1)],
            "level_winner": self.level_winner,
            "level_winner_name": self._name_of(self.level_winner),
            "break_ready": sorted(self._break_ready),
            "seats": seats,
            "ball": round(self.ball, 1),
            "speed": round(self.speed, 1),
            "speed_ratio": round(max(0.0, min(1.0, (self.speed - base) / (self.MAX_SPEED - base))), 2),
            "players": [
                {
                    "id": player.id,
                    "name": player.name,
                    "color": list(player.color),
                    "side": "left" if index == 0 else "right",
                }
                for index, player in enumerate(self.players)
            ],
        })
        return state
