"""Music visualizer rendering behavior mixed into the arcade manager.

The host owns lifecycle, audio input, settings, and visualizer state; this
module owns the frame drawing and beat tracking algorithms.
"""

import math

from led.colors import hsv_to_rgb
from arcade.music_colors import blend_rgb as _blend_rgb
from arcade.music_patterns import MusicPatternMixin


class MusicRenderingMixin(MusicPatternMixin):
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
