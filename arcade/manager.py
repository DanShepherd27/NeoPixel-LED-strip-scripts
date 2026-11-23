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
from led.web_audio import WebMicQueue
from arcade.music_rendering import MusicRenderingMixin
from arcade.song.library import load_song
from arcade.song.session import SongSession

from config import (
    LED_COUNT,
    IDLE_ANIMATION_DURATION,
    IDLE_RANDOM_ORDER,
    COUNTDOWN_SECONDS,
    RESULTS_DURATION,
    LED_ORIENTATION,
    SONG_AUDIO_LATENCY_MS,
    OUTPUT_AUDIO_DEVICE,
)

log = logging.getLogger("arcade.manager")

# Phones heartbeat every 5 s; throttled background tabs can be slower.
PLAYER_AWAY_SECONDS = 20
PLAYER_DROP_SECONDS = 120


def _parse_hex_color(value):
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        raise ValueError("Colors must use #RRGGBB format.")
    try:
        return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))
    except ValueError as exc:
        raise ValueError("Colors must use #RRGGBB format.") from exc


class ArcadeManager(MusicRenderingMixin):
    def __init__(self, count=LED_COUNT, audio_input=None, mic_handoff_seconds=120,
                 music_animation="center_pulse", music_sensitivity=1.0,
                 music_primary_color="#00E5FF", music_accent_color="#FF2EA6",
                 music_beat_lead_ms=0, music_band_colors=None,
                 music_sound_profile="small_speakers",
                 music_glitter_brightness=255, music_glitter_every_beats=8):
        self.count = count
        self.audio_input = audio_input
        self.web_mics = WebMicQueue(mic_handoff_seconds)
        self._music_pi_enabled = False
        self.music_animation = music_animation
        self.music_sensitivity = float(music_sensitivity)
        self.music_sound_profile = music_sound_profile
        self.music_glitter_brightness = max(0, min(255, int(music_glitter_brightness)))
        self.music_glitter_every_beats = music_glitter_every_beats
        self.music_primary_color = music_primary_color.upper()
        self.music_accent_color = music_accent_color.upper()
        self._music_primary_rgb = _parse_hex_color(self.music_primary_color)
        self._music_accent_rgb = _parse_hex_color(self.music_accent_color)
        self.music_band_colors = [
            color.upper() for color in (music_band_colors or (
                "#FF2C0C", "#FF7A00", "#FFDC00", "#24FF20", "#00CDFF", "#AA20FF",
            ))
        ]
        self._music_band_rgb = [_parse_hex_color(color) for color in self.music_band_colors]
        self.music_beat_lead_ms = int(music_beat_lead_ms)
        self._music_phase = 0.0
        self._music_beat_clock = 0.0
        self._music_beat_last_onset = None
        self._music_beat_onset_count = 0
        self._music_downbeat_phase = 1
        self._music_downbeat_scores = [0.0] * 4
        self._music_beat_bar_strengths = []
        self._music_beat_period = None
        self._music_beat_confidence = 0.0
        self._music_beat_low = 0.0
        self._music_beat_pulse = 0.0
        self._music_onset_history = []
        self._music_onset_sample_clock = 0.0
        self._music_onset_sample_value = 0.0
        self._music_tempo_update_clock = 0.0
        self._music_tempo_candidate = None
        self._music_tempo_candidate_hits = 0
        self._retro_vu_peak_position = 0.0
        self._retro_vu_peak_hold = 0.0
        self._retro_vu_level = 0.0
        self._music_band_levels = [0.0] * 6
        self._music_band_peaks = [0.0] * 6
        self._music_band_holds = [0.0] * 6
        self.music_enabled_bands = [True] * 6
        self._bpm_trace_position = 0.0
        self._bpm_trace_energy = 0.0
        self._kitt_position = 0.0
        self._kitt_direction = 1.0
        self._kitt_speak = 0.0
        self._music_led_frame = [(0, 0, 0)] * count
        self._laser_phrase = 0
        self._laser_phrase_length = 4
        self._laser_phrase_index = -1
        self._laser_color_index = 0
        self._laser_energy = 0.0
        self._laser_last_phrase = -1
        self._laser_call_side = 0
        self._laser_group_mode = False
        self._laser_motion = 0.0
        self._laser_target = 0.0
        self._laser_step = 0
        self._laser_previous_bands = [0.0] * 6
        self._laser_kick = 0.0
        self._laser_snare = 0.0
        self._laser_last_kick = -10.0
        self._laser_last_snare = -10.0
        self._laser_volume = 0.0
        self._laser_wave = 0.0
        self._laser_wave_origin = 0.0
        self._laser_scan = 0.0
        self.state = ArcadeState.IDLE
        self._song = None
        self.song_audio_latency_ms = SONG_AUDIO_LATENCY_MS
        self.song_auto_sync = True
        self.song_calibration = {"status": "idle"}
        self.on_song_latency_changed = None  # set by the web layer to persist changes
        self.import_jobs = None              # set by the web layer (song uploads)
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

        self._presence_timer = 0.0
        self.kicked_ids = []        # recently vote-kicked players, so their phone can say why
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
            self._after_departure()

    def vote_kick(self, voter_id, target_id):
        """Toggle a vote to remove a player; a majority of the others removes them.

        Returns the removed player, or None while the vote is still open.
        """
        with self._lock:
            if self.state in (ArcadeState.IDLE, ArcadeState.MUSIC, ArcadeState.SONG):
                return None
            target = self.players.get(target_id)
            if target is None or not self.players.toggle_kick_vote(voter_id, target_id):
                return None
            log.info("Vote kick removed %s (%s)", target.name, target_id)
            self.kicked_ids.append(target_id)
            del self.kicked_ids[:-20]
            self.leave_player(target_id)
            return target

    def _after_departure(self):
        """Keep the lifecycle consistent after someone leaves or is dropped."""
        if self.state not in (ArcadeState.LOBBY, *self._GAME_STATES, ArcadeState.RESULTS):
            return
        if self.players.count() == 0:
            self._enter_idle()
        elif self.state in self._GAME_STATES and not self._participants_present():
            # Nobody left who can play this game: give the seats to the queue.
            self.game = None
            self.game_class = None
            self._enter_lobby()

    _GAME_STATES = (ArcadeState.TUTORIAL, ArcadeState.COUNTDOWN, ArcadeState.GAME)

    def _participants_present(self):
        return any(self.players.get(p.id) for p in (self.game.players if self.game else []))

    def touch(self, player_id):
        self.players.touch(player_id)

    def mark_disconnected(self, player_id):
        self.players.mark_disconnected(player_id)

    def set_ready(self, player_id, ready):
        with self._lock:
            tutorial_done = (
                self.state == ArcadeState.TUTORIAL and self.game_class is not None and
                self.tutorial_index >= len(self.game_class.tutorial_steps)
            )
            if (self.state == ArcadeState.LOBBY or tutorial_done) and self._is_participant(player_id):
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
            if self.state != ArcadeState.IDLE:
                return False
            self.selected_game = None
            self.game = None
            self.game_class = None
            self._music_beat_clock = 0.0
            self._music_beat_last_onset = None
            self._music_beat_period = None
            self._music_beat_confidence = 0.0
            self._music_beat_low = 0.0
            self._music_beat_pulse = 0.0
            self._music_beat_onset_count = 0
            self._music_downbeat_phase = 1
            self._music_downbeat_scores = [0.0] * 4
            self._music_beat_bar_strengths.clear()
            self._music_onset_history.clear()
            self._music_onset_sample_clock = 0.0
            self._music_onset_sample_value = 0.0
            self._music_tempo_update_clock = 0.0
            self._music_tempo_candidate = None
            self._music_tempo_candidate_hits = 0
            if self.audio_input is not None:
                self.audio_input.set_enabled(True)
                self._music_pi_enabled = True
            self.state = ArcadeState.MUSIC
            log.info("State -> MUSIC (microphone visualizer)")
            return True

    def stop_music_mode(self):
        with self._lock:
            if self.audio_input is not None:
                self.audio_input.set_enabled(False)
                self._music_pi_enabled = False
            self.web_mics.reset()
            if self.state == ArcadeState.MUSIC:
                self.state = ArcadeState.IDLE
                log.info("State -> IDLE (music visualizer stopped)")

    def start_song(self, pi_audio=True, song_id=None):
        """Start a song's light show; only possible while idle. Raises KeyError for an unknown song."""
        with self._lock:
            if self.state == ArcadeState.SONG:
                return True
            if self.state != ArcadeState.IDLE:
                return False
            song = load_song(song_id)
            if song is None:
                raise KeyError(song_id)
            self._begin_song(pi_audio, calibrate=False, song=song)
            return True

    def start_song_calibration(self):
        """Play the intro and measure speaker-to-microphone latency (idle only)."""
        with self._lock:
            if self.state != ArcadeState.IDLE:
                return False, "Latency can only be measured while the arcade is idle."
            if self.audio_input is None:
                return False, "No microphone is configured on the Pi."
            self.song_calibration = {"status": "running"}
            self._begin_song(True, calibrate=True, song=load_song())
            return True, None

    def _begin_song(self, pi_audio, calibrate, song):
        self._song = SongSession(
            self.count, pi_audio, self.song_audio_latency_ms, OUTPUT_AUDIO_DEVICE,
            song=song, mic=self.audio_input, auto_sync=self.song_auto_sync, calibrate=calibrate,
        )
        self.state = ArcadeState.SONG
        log.info("State -> SONG (pi_audio=%s, calibrate=%s, error=%s)",
                 pi_audio, calibrate, self._song.pi_audio_error)

    def control_song(self, action, position=None):
        """Transport controls for the running song: pause, resume or seek."""
        with self._lock:
            if self.state != ArcadeState.SONG or self._song is None or self._song.calibrating:
                return False
            if action == "pause":
                self._song.pause()
            elif action == "resume":
                self._song.resume()
            elif action == "seek":
                self._song.seek(float(position))
            else:
                raise ValueError("Unknown song control.")
            return True

    def stop_song(self):
        with self._lock:
            self._stop_song_session()
            if self.state == ArcadeState.SONG:
                self.state = ArcadeState.IDLE
                log.info("State -> IDLE (song stopped)")

    def _stop_song_session(self):
        song, self._song = self._song, None
        if song is None:
            return
        song.stop()
        if song.calibrating:
            self._finish_calibration(song)
        elif song.sync_enabled and abs(song.latency_ms - self.song_audio_latency_ms) >= 3:
            # Auto-sync learned a better latency during the song: keep it.
            self._set_song_latency(song.latency_ms)
        if self.audio_input is not None and self.state != ArcadeState.MUSIC:
            self.audio_input.set_enabled(False)

    def _finish_calibration(self, song):
        result = song.calibration_result or {"ok": False, "message": "Measurement was cancelled."}
        if result["ok"]:
            self._set_song_latency(result["latency_ms"])
            result = dict(result, applied_ms=self.song_audio_latency_ms)
        self.song_calibration = {"status": "done" if result["ok"] else "error", **result}
        log.info("Song latency calibration: %s", {k: v for k, v in result.items() if k != "curve"})

    def _set_song_latency(self, milliseconds):
        self.song_audio_latency_ms = int(round(milliseconds))
        if self.on_song_latency_changed is not None:
            self.on_song_latency_changed(self.song_audio_latency_ms)

    def start_game(self):
        with self._lock:
            if (self.state == ArcadeState.LOBBY and self.selected_game and
                    self._lobby_ready(GAMES[self.selected_game])):
                self._enter_tutorial()

    def rematch(self):
        with self._lock:
            if self.state == ArcadeState.RESULTS and self.selected_game and not self._queue():
                self._enter_tutorial()

    def tutorial_next(self, player_id=None):
        """Advance the demo one step; the last step hands over to ready/countdown."""
        with self._lock:
            if self.state != ArcadeState.TUTORIAL or self.game_class is None:
                return
            if player_id is not None and not self._is_participant(player_id):
                return
            if self.tutorial_index >= len(self.game_class.tutorial_steps):
                return
            self.tutorial_index += 1
            self.tutorial_elapsed = 0.0
            if self.tutorial_index >= len(self.game_class.tutorial_steps) and self._is_solo():
                self._enter_countdown()

    def skip_tutorial(self, player_id=None):
        with self._lock:
            if player_id is not None and not self._is_participant(player_id):
                return
            if self.state == ArcadeState.TUTORIAL and self.game_class:
                self.tutorial_index = 0
                self.tutorial_elapsed = 0.0
                self.players.reset_ready()

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

    def set_music_visualizer(self, animation, sensitivity, primary_color=None, accent_color=None,
                             enabled_bands=None, band_colors=None):
        if animation not in (
            "center_pulse", "mirror_bars", "rainbow_wave", "comet",
            "retro_vu", "inward_diamonds", "red_shades", "live_band",
            "bpm_trace", "laser_dance", "kitt_scanner", "christmas_glitter",
        ):
            raise ValueError("Unknown music animation.")
        if not 0.25 <= float(sensitivity) <= 4.0:
            raise ValueError("Music sensitivity must be between 0.25 and 4.0.")
        primary_color = primary_color or self.music_primary_color
        accent_color = accent_color or self.music_accent_color
        primary_rgb = _parse_hex_color(primary_color)
        accent_rgb = _parse_hex_color(accent_color)
        if enabled_bands is None:
            enabled_bands = self.music_enabled_bands
        if (not isinstance(enabled_bands, (list, tuple)) or len(enabled_bands) != 6 or
                any(not isinstance(value, bool) for value in enabled_bands)):
            raise ValueError("Choose which of the six frequency bands to visualize.")
        if band_colors is None:
            band_colors = self.music_band_colors
        if (not isinstance(band_colors, (list, tuple)) or len(band_colors) != 6 or
                not all(isinstance(color, str) and len(color) == 7 and color.startswith("#")
                        for color in band_colors)):
            raise ValueError("Choose a valid color for each frequency band.")
        band_rgb = [_parse_hex_color(color) for color in band_colors]
        with self._lock:
            if animation != self.music_animation:
                self._retro_vu_peak_position = 0.0
                self._retro_vu_peak_hold = 0.0
                self._retro_vu_level = 0.0
                self._music_band_levels = [0.0] * 6
                self._music_band_peaks = [0.0] * 6
                self._music_band_holds = [0.0] * 6
            self.music_animation = animation
            self.music_sensitivity = float(sensitivity)
            self.music_primary_color = primary_color.upper()
            self.music_accent_color = accent_color.upper()
            self._music_primary_rgb = primary_rgb
            self._music_accent_rgb = accent_rgb
            self.music_enabled_bands = list(enabled_bands)
            self.music_band_colors = [color.upper() for color in band_colors]
            self._music_band_rgb = band_rgb

    def handle_input(self, player_id, action):
        """Queue a player input; processed by the render loop next frame."""
        self._input_queue.put((player_id, action))

    # -- lifecycle transitions (must hold self._lock) ------------------------
    def _enter_idle(self, clear_players=True):
        self._stop_song_session()
        if self.audio_input is not None:
            self.audio_input.set_enabled(False)
            self._music_pi_enabled = False
        self.web_mics.reset()
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
        participants = self._select_players(self.game_class)
        self.game = self.game_class(self)
        self.game.setup(participants)
        self.tutorial_index = 0
        self.tutorial_elapsed = 0.0
        self.players.reset_ready()
        self.state = ArcadeState.TUTORIAL
        log.info("State -> TUTORIAL (%s)", self.selected_game)

    def _start_game(self):
        if self.game is None or self.game_class is None:
            self.game_class = GAMES[self.selected_game]
            participants = self._select_players(self.game_class)
            self.game = self.game_class(self)
            self.game.setup(participants)
        self.game.start()
        self.state = ArcadeState.GAME
        log.info("State -> GAME (%s) with %d players",
                 self.game.name, len(self.game.players))

    def _enter_results(self):
        self.state = ArcadeState.RESULTS
        self.results_timer = RESULTS_DURATION
        log.info("State -> RESULTS (winner=%s)", self.game.winner)

    def _select_players(self, game_class):
        """The first players to join, up to the game's limit, play; the rest queue."""
        connected = self.players.connected_players() or self.players.players()
        limit = getattr(game_class, "max_players", None)
        return connected[:limit] if limit is not None else connected

    def _participants(self):
        """Players of the running (or about to run) game."""
        if self.game is not None:
            return list(self.game.players)
        return self._select_players(self.game_class) if self.game_class else []

    def _lobby_participants(self):
        """Who plays: the selected game's seats in the lobby, else the running game's players."""
        if self.state != ArcadeState.LOBBY and self.game is not None:
            return list(self.game.players)
        game_class = GAMES.get(self.selected_game)
        return self._select_players(game_class) if game_class else self.players.connected_players()

    def _is_participant(self, player_id):
        return any(p.id == player_id for p in self._lobby_participants())

    def _is_solo(self):
        """A game played by one person needs no ready-up."""
        return len(self._participants()) == 1

    def _participants_ready(self):
        participants = self._participants()
        return (len(participants) >= self.game_class_min_players() and
                all(p.ready and p.connected for p in participants))

    def _lobby_ready(self, game_class):
        participants = self._select_players(game_class)
        if len(participants) < game_class.min_players:
            return False
        return len(participants) == 1 or all(p.ready for p in participants)

    def _queue(self):
        """Players waiting for a free seat, in join order."""
        if self.state == ArcadeState.IDLE:
            return []
        taken = {p.id for p in self._lobby_participants()}
        return [p for p in self.players.connected_players() if p.id not in taken]

    # -- per-frame update / render (called by the renderer thread) ----------
    def _process_inputs(self):
        while True:
            try:
                player_id, action = self._input_queue.get_nowait()
            except queue.Empty:
                break
            self.players.touch(player_id)
            if (self.state == ArcadeState.GAME and self.game is not None and
                    any(p.id == player_id for p in self.game.players)):
                try:
                    self.game.handle_input(player_id, action)
                except Exception:
                    log.exception("Game input handler failed")

    def render(self, frame, dt):
        with self._lock:
            self._refresh_presence(dt)
            self._process_inputs()

            if self.state == ArcadeState.IDLE:
                self._update_idle(dt)
                self.current_effect.render(frame, dt)
            elif self.state == ArcadeState.LOBBY:
                self._render_lobby(frame, dt)
            elif self.state == ArcadeState.MUSIC:
                self._render_music(frame, dt)
            elif self.state == ArcadeState.SONG:
                self._render_song(frame, dt)
            elif self.state == ArcadeState.TUTORIAL:
                self._update_tutorial(dt)
                if self.state == ArcadeState.TUTORIAL and self.game is not None:
                    steps = self.game_class.tutorial_steps
                    if self.tutorial_index < len(steps):
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
            self._music_led_frame = list(frame.pixels)

    def _refresh_presence(self, dt):
        self._presence_timer -= dt
        if self._presence_timer > 0:
            return
        self._presence_timer = 1.0
        dropped = self.players.refresh_presence(PLAYER_AWAY_SECONDS, PLAYER_DROP_SECONDS)
        if dropped:
            self._after_departure()

    def _render_song(self, frame, dt):
        song = self._song
        if song is not None:
            song.update()
        if song is None or song.finished:
            self.stop_song()
            return
        song.render(frame, dt)

    # -- state updates -------------------------------------------------------
    def _update_idle(self, dt):
        self._idle_timer -= dt
        if self._idle_timer <= 0:
            self._next_idle()

    def _update_tutorial(self, dt):
        """Loop the current step's demo until a player presses Next."""
        steps = self.game_class.tutorial_steps
        if self.tutorial_index >= len(steps):
            if self._participants_ready():
                self._enter_countdown()
            return
        duration = max(0.1, float(steps[self.tutorial_index]["duration"]))
        self.tutorial_elapsed = (self.tutorial_elapsed + dt) % duration

    def game_class_min_players(self):
        return int(getattr(self.game_class, "min_players", 1))

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
            self._finish_results()

    def _finish_results(self):
        """Hand the strip to whoever was waiting; otherwise go idle."""
        waiting = self._queue()
        if not waiting:
            self._enter_idle(clear_players=True)
            return
        self.players.send_to_back([p.id for p in self.game.players])
        self.game = None
        self.game_class = None
        self._enter_lobby()

    # -- rendering helpers ---------------------------------------------------
    def _render_lobby(self, frame, dt):
        players = self._lobby_participants()
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
        results = {}
        if self.game is not None and self.game.winner:
            winner = self.players.get(self.game.winner)
            results = self.game.results or {}
        color = winner.color if winner else tuple(results.get("winner_color", (255, 255, 255)))
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
                    results = self.game.results or {}
                    game_state["winner_name"] = winner.name if winner else results.get("winner_name")
                    game_state["winner_color"] = (
                        list(winner.color) if winner else results.get("winner_color"))

            return {
                "state": self.state.value,
                "players": self._players_snapshot(),
                "ready_required": self._ready_required(),
                "kicked": list(self.kicked_ids),
                "idle_animation": self.current_idle_name,
                "led_orientation": LED_ORIENTATION,
                "preview_invert_order": getattr(self, "preview_invert_order", False),
                "games": game_catalog(),
                "selected_game": self.selected_game,
                "countdown": round(max(0.0, self.countdown), 1),
                "tutorial": self._tutorial_snapshot(),
                "audio": self._audio_snapshot(),
                "web_mic": self.web_mics.snapshot(),
                "music_visualizer": {
                    "animation": self.music_animation,
                    "sensitivity": self.music_sensitivity,
                    "primary_color": self.music_primary_color,
                    "accent_color": self.music_accent_color,
                    "enabled_bands": list(self.music_enabled_bands),
                    "band_colors": list(self.music_band_colors),
                    "bpm": (
                        int(round(60.0 / self._music_beat_period))
                        if self._music_beat_period and self._music_beat_confidence >= 0.25
                        else None
                    ),
                    "beat_lead_ms": self.music_beat_lead_ms,
                    "glitter_brightness": self.music_glitter_brightness,
                },
                "song": self._song.snapshot() if self._song else None,
                "song_calibration": self.song_calibration,
                "song_imports": self.import_jobs.snapshot() if self.import_jobs else [],
                "song_latency_ms": self.song_audio_latency_ms,
                "music_led_frame": [list(pixel) for pixel in self._music_led_frame],
                "pi_audio": self.audio_input.snapshot() if self.audio_input else {
                    "status": "unavailable", "error": "No audio input configured.",
                    "level": 0.0, "peak": 0.0, "clap": False,
                },
                "game": game_state,
                "results": self.game.results if self.game else None,
            }

    def _ready_required(self):
        """False while the selected game would be played by one person."""
        if self.state == ArcadeState.LOBBY:
            return len(self._lobby_participants()) > 1
        return not self._is_solo() if self.game_class else True

    def _players_snapshot(self):
        queued = {p.id: position for position, p in enumerate(self._queue(), start=1)}
        snapshot = self.players.snapshot()
        for entry in snapshot:
            entry["queue_position"] = queued.get(entry["id"], 0)
            entry["queued"] = entry["id"] in queued
        return snapshot

    def _audio_snapshot(self):
        web_audio = self.web_mics.snapshot()
        if web_audio["active"]:
            return dict(web_audio, source="web")
        if self.audio_input:
            return dict(self.audio_input.snapshot(), source="pi")
        return {
            "status": "unavailable", "error": "No audio input configured.",
            "level": 0.0, "peak": 0.0, "clap": False, "source": "none",
        }

    def _tutorial_snapshot(self):
        if self.state != ArcadeState.TUTORIAL or self.game_class is None:
            return None
        steps = self.game_class.tutorial_steps
        if self.tutorial_index >= len(steps):
            return {
                "index": len(steps), "count": len(steps),
                "title": "Everyone ready?",
                "instruction": "Review or replay the demo, then mark yourself ready. The game starts when everyone is ready.",
                "remaining": 0.0, "waiting_ready": True,
            }
        if not steps:
            return {"index": 0, "count": 0, "title": "Get ready",
                    "instruction": "The game is about to begin.", "remaining": 0.0}
        step = steps[self.tutorial_index]
        return {
            "index": self.tutorial_index + 1,
            "count": len(steps),
            "title": step["title"],
            "instruction": step["instruction"],
            "remaining": 0.0,
            "is_last": self.tutorial_index == len(steps) - 1,
        }
