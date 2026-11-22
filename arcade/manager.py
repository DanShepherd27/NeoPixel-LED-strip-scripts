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
import math

from arcade.state import ArcadeState
from arcade.players import PlayerManager
from arcade.games import GAMES, game_catalog
from led.effects import EFFECTS
from led.colors import hsv_to_rgb
from led.web_audio import WebMicQueue

from config import (
    LED_COUNT,
    IDLE_ANIMATION_DURATION,
    IDLE_RANDOM_ORDER,
    COUNTDOWN_SECONDS,
    RESULTS_DURATION,
    LED_ORIENTATION,
)

log = logging.getLogger("arcade.manager")


def _parse_hex_color(value):
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        raise ValueError("Colors must use #RRGGBB format.")
    try:
        return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))
    except ValueError as exc:
        raise ValueError("Colors must use #RRGGBB format.") from exc


def _blend_rgb(start, end, amount):
    amount = max(0.0, min(1.0, amount))
    return tuple(int(round(a + (b - a) * amount)) for a, b in zip(start, end))


class ArcadeManager:
    def __init__(self, count=LED_COUNT, audio_input=None, mic_handoff_seconds=120,
                 music_animation="center_pulse", music_sensitivity=1.0,
                 music_primary_color="#00E5FF", music_accent_color="#FF2EA6",
                 music_beat_lead_ms=0):
        self.count = count
        self.audio_input = audio_input
        self.web_mics = WebMicQueue(mic_handoff_seconds)
        self._music_pi_enabled = False
        self.music_animation = music_animation
        self.music_sensitivity = float(music_sensitivity)
        self.music_primary_color = music_primary_color.upper()
        self.music_accent_color = music_accent_color.upper()
        self._music_primary_rgb = _parse_hex_color(self.music_primary_color)
        self._music_accent_rgb = _parse_hex_color(self.music_accent_color)
        self.music_beat_lead_ms = int(music_beat_lead_ms)
        self._music_phase = 0.0
        self._music_beat_clock = 0.0
        self._music_beat_last_onset = None
        self._music_beat_period = None
        self._music_beat_confidence = 0.0
        self._music_beat_low = 0.0
        self._music_beat_pulse = 0.0
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
        self.state = ArcadeState.IDLE
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
            if self.state == ArcadeState.LOBBY and self.players.count() == 0:
                self._enter_idle()

    def touch(self, player_id):
        self.players.touch(player_id)

    def mark_disconnected(self, player_id):
        self.players.mark_disconnected(player_id)

    def set_ready(self, player_id, ready):
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

    def start_game(self):
        with self._lock:
            if self.state == ArcadeState.LOBBY and self.selected_game:
                self._enter_tutorial()

    def rematch(self):
        with self._lock:
            if self.state == ArcadeState.RESULTS and self.selected_game:
                self._enter_tutorial()

    def skip_tutorial(self):
        with self._lock:
            if self.state == ArcadeState.TUTORIAL:
                self._enter_countdown()

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
                             enabled_bands=None):
        if animation not in (
            "center_pulse", "mirror_bars", "rainbow_wave", "comet",
            "retro_vu", "inward_diamonds", "red_shades", "live_band",
            "bpm_trace", "laser_dance", "kitt_scanner",
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

    def handle_input(self, player_id, action):
        """Queue a player input; processed by the render loop next frame."""
        self._input_queue.put((player_id, action))

    # -- lifecycle transitions (must hold self._lock) ------------------------
    def _enter_idle(self, clear_players=True):
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
        self.game = self.game_class(self)
        self.game.setup(self._participants())
        self.tutorial_index = 0
        self.tutorial_elapsed = 0.0
        self.state = ArcadeState.TUTORIAL
        log.info("State -> TUTORIAL (%s)", self.selected_game)

    def _start_game(self):
        if self.game is None or self.game_class is None:
            self.game_class = GAMES[self.selected_game]
            self.game = self.game_class(self)
            self.game.setup(self._participants())
        self.game.start()
        self.state = ArcadeState.GAME
        log.info("State -> GAME (%s) with %d players",
                 self.game.name, len(self.game.players))

    def _enter_results(self):
        self.state = ArcadeState.RESULTS
        self.results_timer = RESULTS_DURATION
        log.info("State -> RESULTS (winner=%s)", self.game.winner)

    def _participants(self):
        """Pick the players for the current game based on its constraints."""
        connected = self.players.connected_players()
        if not connected:
            connected = self.players.players()
        limit = self.game_class.max_players
        if limit is not None:
            connected = connected[:limit]
        return connected

    # -- per-frame update / render (called by the renderer thread) ----------
    def _process_inputs(self):
        while True:
            try:
                player_id, action = self._input_queue.get_nowait()
            except queue.Empty:
                break
            self.players.touch(player_id)
            if self.state == ArcadeState.GAME and self.game is not None:
                try:
                    self.game.handle_input(player_id, action)
                except Exception:
                    log.exception("Game input handler failed")

    def render(self, frame, dt):
        with self._lock:
            self._process_inputs()

            if self.state == ArcadeState.IDLE:
                self._update_idle(dt)
                self.current_effect.render(frame, dt)
            elif self.state == ArcadeState.LOBBY:
                self._render_lobby(frame, dt)
            elif self.state == ArcadeState.MUSIC:
                self._render_music(frame, dt)
            elif self.state == ArcadeState.TUTORIAL:
                self._update_tutorial(dt)
                if self.state == ArcadeState.TUTORIAL and self.game is not None:
                    steps = self.game_class.tutorial_steps
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

    # -- state updates -------------------------------------------------------
    def _update_idle(self, dt):
        self._idle_timer -= dt
        if self._idle_timer <= 0:
            self._next_idle()

    def _render_music(self, frame, dt):
        web_audio = self.web_mics.snapshot()
        use_pi = not web_audio["active"]
        if self.audio_input is not None and self._music_pi_enabled != use_pi:
            self.audio_input.set_enabled(use_pi)
            self._music_pi_enabled = use_pi
        audio = web_audio if web_audio["active"] else (
            self.audio_input.snapshot() if self.audio_input else {}
        )
        level = max(0.0, min(1.0, float(audio.get("level", 0.0)) * self.music_sensitivity))
        peak = max(0.0, min(1.0, float(audio.get("peak", 0.0)) * self.music_sensitivity))
        bands = audio.get("bands", [level] * 6)
        if not isinstance(bands, (list, tuple)) or len(bands) != 6:
            bands = [level] * 6
        bands = [
            max(0.0, min(1.0, float(value) * self.music_sensitivity))
            for value in bands
        ]
        self._music_phase += dt
        beat_pulse = self._update_music_beat(
            bands, audio.get("latency_ms", 16), dt,
        )
        self._draw_music_animation(frame, level, peak, dt, bands)

        if beat_pulse > 0 and self.music_animation not in ("live_band", "laser_dance", "kitt_scanner"):
            flash_color = (
                (255, 70, 0) if self.music_animation in ("retro_vu", "live_band")
                else self._music_accent_rgb
            )
            amount = min(0.28, 0.28 * beat_pulse)
            for index in range(frame.count):
                frame.blend(index, flash_color, amount)

        if audio.get("clap"):
            self._music_clap_flash = 0.13
        else:
            self._music_clap_flash = max(0.0, getattr(self, "_music_clap_flash", 0.0) - dt)
        if self._music_clap_flash > 0 and self.music_animation not in ("live_band", "laser_dance", "kitt_scanner"):
            amount = min(0.32, self._music_clap_flash / 0.13 * 0.32)
            if self.music_animation == "red_shades":
                flash_color = (255, 0, 0)
            elif self.music_animation in ("retro_vu", "rainbow_wave"):
                flash_color = (255, 80, 12)
            else:
                flash_color = self._music_accent_rgb
            for index in range(frame.count):
                frame.blend(index, flash_color, amount)

    def _update_music_beat(self, bands, latency_ms, dt):
        """Track bass onsets and pulse slightly ahead of the predicted next beat."""
        dt = max(0.0, dt)
        self._music_beat_clock += dt
        now = self._music_beat_clock
        bass = max(bands[0], bands[1] * 0.88)
        previous = self._music_beat_low
        self._music_beat_low += (bass - previous) * min(1.0, dt / 0.045)
        rise = self._music_beat_low - previous
        self._music_beat_pulse = max(0.0, self._music_beat_pulse - dt / 0.11)

        onset = self._music_beat_low >= 0.22 and rise >= 0.10
        if onset and (
            self._music_beat_last_onset is None
            or now - self._music_beat_last_onset >= 0.27
        ):
            if self._music_beat_last_onset is not None:
                interval = now - self._music_beat_last_onset
                if 0.30 <= interval <= 1.50:
                    self._music_beat_period = (
                        interval if self._music_beat_period is None
                        else self._music_beat_period * 0.72 + interval * 0.28
                    )
                    self._music_beat_confidence = min(
                        1.0, self._music_beat_confidence + 0.28,
                    )
                else:
                    self._music_beat_confidence *= 0.5
            self._music_beat_last_onset = now
            self._music_beat_pulse = min(1.0, 0.45 + rise * 2.0)

        if self._music_beat_last_onset is None:
            return self._music_beat_pulse
        silence = now - self._music_beat_last_onset
        if silence > 2.5:
            self._music_beat_confidence = max(
                0.0, self._music_beat_confidence - dt * 0.35,
            )
            if self._music_beat_confidence == 0.0:
                self._music_beat_period = None

        period = self._music_beat_period
        if period is None or self._music_beat_confidence < 0.25 or silence > 2.5:
            return self._music_beat_pulse

        try:
            mic_latency_ms = max(0.0, min(500.0, float(latency_ms)))
        except (TypeError, ValueError):
            mic_latency_ms = 16.0
        lead = max(-0.15, min(
            0.35, (mic_latency_ms + 25.0 + self.music_beat_lead_ms) / 1000.0,
        ))
        beat_number = max(
            1, int((now + lead - self._music_beat_last_onset) / period) + 1,
        )
        beat_time = self._music_beat_last_onset + beat_number * period
        until_predicted = beat_time - lead - now
        if -0.025 <= until_predicted <= 0.11:
            predicted_pulse = max(0.0, 1.0 - max(0.0, until_predicted) / 0.11)
            self._music_beat_pulse = max(self._music_beat_pulse, predicted_pulse)
        return self._music_beat_pulse

    def _draw_music_animation(self, frame, level, peak, dt=0.0, bands=None):
        count = self.count
        if not count:
            return
        if self.music_animation == "live_band":
            self._draw_live_band(frame, bands or [level] * 6, dt)
            return
        if self.music_animation == "bpm_trace":
            frame.clear()
            period = self._music_beat_period
            if period and self._music_beat_confidence >= 0.25 and self._music_beat_last_onset is not None:
                elapsed = max(0.0, self._music_beat_clock - self._music_beat_last_onset)
                phase = (elapsed / period) % 1.0
                self._bpm_trace_position = (phase * count) % count
                attack = min(1.0, self._music_beat_pulse * 4.0)
                self._bpm_trace_energy = max(attack, self._bpm_trace_energy * math.exp(-max(0.0, dt) * 11.0))
            else:
                self._bpm_trace_energy *= math.exp(-max(0.0, dt) * 3.0)
            marker = int(self._bpm_trace_position) % count
            frame.set(marker, (255, 255, 255))
            tail = (marker - 1) % count
            frame.set(tail, (0, int(170 * self._bpm_trace_energy), int(255 * self._bpm_trace_energy)))
            return
        if self.music_animation == "kitt_scanner":
            frame.clear()
            # A classic KITT scanner sweeps continuously between the ends.
            # The original's quick, lateral sweep is kept at roughly 1.55 s
            # end-to-end. Music may only add a small amount of urgency.
            speed = 38.0 + level * 5.0 + self._music_beat_pulse * 2.0
            self._kitt_position += self._kitt_direction * speed * max(0.0, dt)
            if self._kitt_position >= count - 1:
                self._kitt_position = count - 1
                self._kitt_direction = -1.0
            elif self._kitt_position <= 0:
                self._kitt_position = 0.0
                self._kitt_direction = 1.0
            head = int(round(self._kitt_position))
            transient = max(
                self._music_beat_pulse,
                max(0.0, peak - level * 0.62) * 3.2,
            )
            self._kitt_speak = max(transient, self._kitt_speak * math.exp(-max(0.0, dt) * 13.0))
            for offset in range(-3, 4):
                index = head + offset
                if not 0 <= index < count:
                    continue
                strength = max(0.0, 1.0 - abs(offset) / 4.0)
                strength = strength * strength
                # Pure KITT red. A transient brightens the head and its two
                # nearest neighbours, like a short spoken emphasis, without
                # coloring any unlit pixels or changing toward amber.
                emphasis = self._kitt_speak if abs(offset) <= 1 else 0.0
                red = int(255 * strength * (0.64 + 0.36 * emphasis))
                frame.set(index, (red, 0, 0))
            return
        if self.music_animation == "laser_dance":
            self._draw_laser_dance(frame, bands or [level] * 6, dt)
            return
        if self.music_animation in ("center_pulse", "mirror_bars", "comet", "inward_diamonds"):
            # These patterns previously used raw RMS directly, which left
            # their sparse shapes nearly invisible at ordinary listening
            # levels. Expand the low/mid range without changing configured
            # sensitivity or the other full-strip patterns.
            level = min(1.0, (level * 1.5) ** 0.82)
            peak = min(1.0, (peak * 1.5) ** 0.82)
        brightness = 0.16 + 0.66 * level
        if self.music_animation == "red_shades":
            for index in range(count):
                wave = (math.sin(index * 0.48 + self._music_phase * 4.0) + 1.0) * 0.5
                red = int(max(8, min(255, 12 + level * 45 + wave * (24 + 174 * level) + peak * 20)))
                frame.set(index, (red, 0, 0))
            return

        if self.music_animation == "rainbow_wave":
            for index in range(count):
                hue = (index * 360.0 / max(1, count) + self._music_phase * 55.0) % 360.0
                frame.set(index, hsv_to_rgb(hue, 1.0, brightness))
            return

        if self.music_animation == "comet":
            head = int(self._music_phase * (3.0 + level * 16.0)) % count
            tail = max(6, int(6 + peak * count * 0.30))
            frame.clear()
            for offset in range(tail):
                index = (head - offset) % count
                amount = (1.0 - offset / tail) * (0.42 + 0.50 * level)
                color = _blend_rgb(self._music_primary_rgb, self._music_accent_rgb, offset / max(1, tail - 1))
                frame.set(index, tuple(int(channel * amount) for channel in color))
            return

        half = (count + 1) // 2
        extent = int(round(level * max(0, half - 1)))
        if self.music_animation == "retro_vu":
            # A vertical strip is a single equalizer column: build it from
            # the bottom with a saturated multicolor VU gradient. Keep a
            # small 8-10 LED idle floor, then exaggerate RMS changes
            # for a playful response. Raw sample peaks can be high in room
            # noise, so only let them boost the bar when RMS confirms sound.
            frame.clear()
            energy = level
            if level >= 0.035:
                energy = max(energy, peak * 0.65)
            target_level = 0.14 + 0.86 * (min(1.0, energy) ** 0.62)
            response = 0.04 if target_level > self._retro_vu_level else 0.10
            blend = min(1.0, max(0.0, dt) / response)
            self._retro_vu_level += (target_level - self._retro_vu_level) * blend
            strip_extent = int(round(self._retro_vu_level * max(0, count - 1)))
            for index in range(max(1, strip_extent + 1)):
                position = index / max(1, count - 1)
                if position >= 0.78:
                    color = (255, 0, 0)       # red peak zone
                elif position >= 0.38:
                    color = (255, 210, 0)     # yellow warning zone
                else:
                    color = (0, 255, 24)      # green normal zone
                frame.set(index, color)

            # Peak marker follows the strongest recent volume. It holds for
            # half a second, then falls at a steady rate until the live level
            # catches it again.
            peak_extent = max(self._retro_vu_level, target_level) * max(0, count - 1)
            if peak_extent >= self._retro_vu_peak_position:
                self._retro_vu_peak_position = peak_extent
                self._retro_vu_peak_hold = 0.5
            elif self._retro_vu_peak_hold > 0:
                self._retro_vu_peak_hold = max(0.0, self._retro_vu_peak_hold - dt)
            else:
                self._retro_vu_peak_position = max(
                    peak_extent, self._retro_vu_peak_position - dt * 16.0,
                )
            if self._retro_vu_peak_position >= 0.5:
                marker = min(count - 1, int(round(self._retro_vu_peak_position)))
                frame.set(marker, (0, 220, 255))
            return

        if self.music_animation == "inward_diamonds":
            frame.clear()
            travel = int((self._music_phase * (6.0 + level * 12.0)) % max(1, half))
            radius = max(3, min(8, 3 + int(peak * 6)))
            for offset in range(-radius, radius + 1):
                intensity = (1.0 - abs(offset) / (radius + 1.0)) * (0.45 + 0.50 * level)
                left = travel + offset
                right = count - 1 - travel - offset
                frame.set(left, tuple(int(channel * intensity) for channel in self._music_primary_rgb))
                frame.set(right, tuple(int(channel * intensity) for channel in self._music_accent_rgb))
            return

        if self.music_animation == "mirror_bars":
            # Discrete saturated blocks grow from the center with the beat.
            frame.clear()
            for offset in range(max(1, extent + 1)):
                color = _blend_rgb(self._music_primary_rgb, self._music_accent_rgb,
                                   offset / max(1, half - 1))
                color = tuple(int(channel * (0.48 + 0.48 * level)) for channel in color)
                frame.set(half - 1 - offset, color)
                frame.set(half + offset, color)
            return

        # Center pulse: a smooth, cool-to-warm gradient expands with volume.
        frame.clear()
        pulse_brightness = 0.34 + 0.62 * level
        for offset in range(max(1, extent + 1)):
            strength = max(0.30, 1.0 - offset / max(2.0, extent + 1.0) * 0.60)
            color = _blend_rgb(self._music_primary_rgb, self._music_accent_rgb,
                               offset / max(1, half - 1))
            color = tuple(int(channel * strength * pulse_brightness) for channel in color)
            frame.set(half - 1 - offset, color)
            frame.set(half + offset, color)

    def _draw_laser_dance(self, frame, bands, dt):
        """Sparse, phrase-based choreography driven by drum-like onsets.

        This is intentionally an interpretation rather than instrument
        separation: low-band attacks are kick-like and mid/high attacks are
        snare-like. Other band energy provides the quieter connective motion.
        """
        frame.clear()
        count = self.count
        bands = [max(0.0, min(1.0, float(value))) for value in bands]
        enabled = [value if self.music_enabled_bands[index] else 0.0
                   for index, value in enumerate(bands)]
        now = self._music_beat_clock
        low = max(enabled[0], enabled[1] * 0.90)
        snare_band = max(enabled[2] * 0.65, enabled[3], enabled[4] * 0.78)
        low_rise = low - max(self._laser_previous_bands[0], self._laser_previous_bands[1] * 0.90)
        snare_rise = snare_band - max(
            self._laser_previous_bands[2] * 0.65,
            self._laser_previous_bands[3], self._laser_previous_bands[4] * 0.78,
        )
        self._laser_previous_bands = list(enabled)

        kick_hit = low >= 0.24 and low_rise >= 0.07 and now - self._laser_last_kick >= 0.22
        snare_hit = (snare_band >= 0.28 and snare_rise >= 0.08 and
                     snare_band >= low * 0.62 and now - self._laser_last_snare >= 0.16)
        if kick_hit:
            self._laser_last_kick = now
            self._laser_kick = 1.0
            self._laser_step += 1
        else:
            self._laser_kick *= math.exp(-max(0.0, dt) * 5.0)
        if snare_hit:
            self._laser_last_snare = now
            self._laser_snare = 1.0
        else:
            self._laser_snare *= math.exp(-max(0.0, dt) * 8.0)

        period = self._music_beat_period or 0.55
        phrase_index = int(now / period) // 8
        if phrase_index != self._laser_phrase_index:
            self._laser_phrase_index = phrase_index
            # A club-like scene lasts eight beats: solo chase, call/answer,
            # mirror sweep, then a grouped run for a higher-energy phrase.
            self._laser_phrase = phrase_index % 4
            self._laser_call_side = phrase_index % 2
            self._laser_color_index = phrase_index % 3

        selected = [value for index, value in enumerate(enabled)
                    if self.music_enabled_bands[index]]
        target_energy = sum(selected) / max(1, len(selected))
        rate = 0.16 if target_energy > self._laser_energy else 1.35
        self._laser_energy += (target_energy - self._laser_energy) * min(1.0, max(0.0, dt) / rate)

        # Audio influences a continuously changing palette. Low energy makes
        # it cooler; mid/high energy opens it toward magenta and violet.
        hue = (190 + 58 * max(enabled[3:]) + 22 * enabled[0] + phrase_index * 17) % 360
        lead_color = hsv_to_rgb(hue, 0.88, 0.96)
        answer_color = hsv_to_rgb((hue + 78) % 360, 0.82, 0.82)
        soft_color = hsv_to_rgb((hue + 32) % 360, 0.72, 0.46)
        section = max(1, count // 4)

        # Kicks advance the choreography; the motion is eased so the strip
        # reads as a chase rather than a strobe.
        if self._laser_phrase == 0:
            path = (2, 10, 19, 29, 40, 50, 57, 47, 36, 25, 14, 5)
        elif self._laser_phrase == 1:
            path = (2, 5, 9, 13, 10, 6)
        elif self._laser_phrase == 2:
            path = (2, 6, 10, 13, 9, 5)
        else:
            path = (2, 5, 8, 11, 13, 10, 7, 4)
        target = path[self._laser_step % len(path)]
        if self._laser_phrase in (1, 3) and self._laser_call_side:
            target = count - 1 - target
        self._laser_target = target
        ease = 0.12 if kick_hit else 0.42
        self._laser_motion += (target - self._laser_motion) * min(1.0, max(0.0, dt) / ease)
        lead = min(count - 1, max(0, int(round(self._laser_motion))))

        def paint_run(center, length, color, strength=1.0):
            start = center - (length - 1) // 2
            for offset in range(length):
                pixel = start + offset
                if 0 <= pixel < count:
                    edge = 1.0 - abs(offset - (length - 1) / 2) / max(1.0, length)
                    frame.set(pixel, tuple(int(channel * strength * (0.68 + edge * 0.32))
                                           for channel in color))

        if self._laser_phrase == 0:
            # Single-color chase: the clearest sound-active club-light cue.
            paint_run(lead, 1, lead_color)
            if self._laser_snare > 0.14:
                paint_run(max(0, lead - 3), 1, answer_color, self._laser_snare * 0.65)
        elif self._laser_phrase == 1:
            # Question/answer: the kick speaks in one outer quarter and the
            # snare replies from the other, leaving both middle quarters dark.
            paint_run(lead, 1, lead_color)
            if self._laser_snare > 0.12:
                paint_run(count - 1 - lead, 1, answer_color, self._laser_snare)
        elif self._laser_phrase == 2:
            # Alternating laser look: two symmetric dancers only occupy the
            # two outer quarters, separated by thirty dark pixels.
            outer = min(section - 1, max(0, lead))
            paint_run(outer, 1, lead_color)
            paint_run(count - 1 - outer, 1, lead_color, 0.82)
        else:
            # Grouped chase for a chorus/drop, still only three adjacent LEDs.
            side_start = 0 if self._laser_call_side == 0 else count - section
            local = min(section - 2, max(1, lead - side_start))
            group = side_start + local
            group_size = 3 if self._laser_energy > 0.48 else 1
            paint_run(group, group_size, lead_color)
            if self._laser_snare > 0.16:
                paint_run(count - 1 - group, 1, answer_color, self._laser_snare * 0.78)

        # A single, dim, slow accent represents melodic/vocal content only
        # when the drums leave space. It never shares a section with a pair.
        mid_energy = max(enabled[2:]) if enabled[2:] else 0.0
        if self._laser_phrase in (0, 3) and self._laser_kick < 0.12 and self._laser_snare < 0.12 and mid_energy > 0.20:
            middle_start = section if self._laser_call_side == 0 else section * 2
            drift = int((math.sin(now * 0.72) + 1.0) * 0.5 * (section - 1))
            paint_run(middle_start + drift, 1, soft_color, min(0.48, mid_energy * 0.55))

    def _draw_live_band(self, frame, bands, dt):
        """Render six frequency bands as independent bars along the 1D strip."""
        frame.clear()
        colors = (
            (255, 44, 12), (255, 122, 0), (255, 220, 0),
            (36, 255, 32), (0, 205, 255), (170, 32, 255),
        )
        bands = [value if self.music_enabled_bands[index] else 0.0
                 for index, value in enumerate(bands)]
        widths = (0.18, 0.16, 0.15, 0.15, 0.16, 0.20)
        for band_index, raw_level in enumerate(bands):
            target = min(1.0, max(0.0, float(raw_level)) * 1.35) ** 0.78
            response = 0.035 if target > self._music_band_levels[band_index] else 0.16
            blend = min(1.0, max(0.0, dt) / response)
            current = self._music_band_levels[band_index]
            current += (target - current) * blend
            self._music_band_levels[band_index] = current

            start = round(sum(widths[:band_index]) * self.count)
            end = round(sum(widths[:band_index + 1]) * self.count)
            segment_size = max(1, end - start)
            capacity = max(1, segment_size - (1 if band_index < 5 else 0))
            lit = int(round(current * capacity))
            if current > 0.035:
                lit = max(1, lit)
            for offset in range(min(capacity, lit)):
                intensity = 0.62 + 0.38 * current
                color = tuple(int(channel * intensity) for channel in colors[band_index])
                frame.set(start + offset, color)

            peak = self._music_band_peaks[band_index]
            if target >= peak:
                peak = target
                self._music_band_holds[band_index] = 0.24
            elif self._music_band_holds[band_index] > 0:
                self._music_band_holds[band_index] = max(
                    0.0, self._music_band_holds[band_index] - dt,
                )
            else:
                peak = max(target, peak - max(0.0, dt) * 1.8)
            self._music_band_peaks[band_index] = peak
            marker = int(round(peak * capacity)) - 1
            if peak > 0.05 and 0 <= marker < capacity:
                frame.set(start + marker, (0, 220, 255))

    def _update_tutorial(self, dt):
        steps = self.game_class.tutorial_steps
        self.tutorial_elapsed += dt
        while self.tutorial_index < len(steps):
            duration = float(steps[self.tutorial_index]["duration"])
            if self.tutorial_elapsed < duration:
                return
            self.tutorial_elapsed -= duration
            self.tutorial_index += 1
        self._enter_countdown()

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
            self._enter_idle(clear_players=True)

    # -- rendering helpers ---------------------------------------------------
    def _render_lobby(self, frame, dt):
        players = self.players.connected_players()
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
        if self.game is not None and self.game.winner:
            winner = self.players.get(self.game.winner)
        color = winner.color if winner else (255, 255, 255)
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
                    game_state["winner_name"] = winner.name if winner else None
                    game_state["winner_color"] = list(winner.color) if winner else None

            return {
                "state": self.state.value,
                "players": self.players.snapshot(),
                "idle_animation": self.current_idle_name,
                "led_orientation": LED_ORIENTATION,
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
                    "bpm": (
                        int(round(60.0 / self._music_beat_period))
                        if self._music_beat_period and self._music_beat_confidence >= 0.25
                        else None
                    ),
                    "beat_lead_ms": self.music_beat_lead_ms,
                },
                "music_led_frame": [list(pixel) for pixel in self._music_led_frame],
                "pi_audio": self.audio_input.snapshot() if self.audio_input else {
                    "status": "unavailable", "error": "No audio input configured.",
                    "level": 0.0, "peak": 0.0, "clap": False,
                },
                "game": game_state,
                "results": self.game.results if self.game else None,
            }

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
        if not steps:
            return {"index": 0, "count": 0, "title": "Get ready",
                    "instruction": "The game is about to begin.", "remaining": 0.0}
        step = steps[self.tutorial_index]
        return {
            "index": self.tutorial_index + 1,
            "count": len(steps),
            "title": step["title"],
            "instruction": step["instruction"],
            "remaining": round(max(0.0, float(step["duration"]) - self.tutorial_elapsed), 1),
        }
