"""Music visualizer rendering behavior mixed into the arcade manager.

The host owns lifecycle, audio input, settings, and visualizer state; this
module owns the frame drawing and beat tracking algorithms.
"""

import math
import time

from led.colors import hsv_to_rgb
from arcade.music_colors import blend_rgb as _blend_rgb
from arcade.music_gain import AutoGain
from arcade.music_beat_patterns import BeatPatternMixin
from arcade.music_patterns import MusicPatternMixin

# Patterns drawn by BeatPatternMixin (``_draw_<name>``).
BEAT_PATTERNS = ("center_pulse", "mirror_bars", "comet", "rainbow_wave", "inward_diamonds", "club")


class MusicRenderingMixin(BeatPatternMixin, MusicPatternMixin):
    def _render_music(self, frame, dt):
        web_audio = self.web_mics.snapshot()
        use_pi = not web_audio["active"]
        if self.audio_input is not None and self._music_pi_enabled != use_pi:
            self.audio_input.set_enabled(use_pi)
            self._music_pi_enabled = use_pi
        audio = web_audio if web_audio["active"] else (
            self.audio_input.snapshot() if self.audio_input else {}
        )
        raw_level = float(audio.get("level", 0.0))
        bands = audio.get("bands", [raw_level] * 6)
        if not isinstance(bands, (list, tuple)) or len(bands) != 6:
            bands = [raw_level] * 6
        # Auto-gain first, so loud music is scaled down rather than clipped and
        # the configured sensitivity still applies on top.
        gained = self._music_gain.apply([raw_level, *bands], dt)
        level = min(1.0, gained[0] * self.music_sensitivity)
        peak = max(0.0, min(1.0, float(audio.get("peak", 0.0)) * self.music_sensitivity))
        bands = [min(1.0, value * self.music_sensitivity) for value in gained[1:]]
        enabled = self.music_enabled_bands
        if self.music_sound_profile == "small_speakers":
            # Small speakers often lose sub-bass. Let low-mid kick harmonics
            # stand in for it, while respecting the user's selected bands.
            low_mid = bands[2] if enabled[2] else 0.0
            if enabled[0]:
                bands[0] = min(1.0, max(bands[0] * 1.45, low_mid * 0.72))
            if enabled[1]:
                bands[1] = min(1.0, max(bands[1] * 1.3, low_mid * 0.55))
        elif self.music_sound_profile == "bass_forward":
            if enabled[0]:
                bands[0] = min(1.0, bands[0] * 1.35)
            if enabled[1]:
                bands[1] = min(1.0, bands[1] * 1.2)
        total_energy = sum(value * value for value in bands)
        selected_energy = sum(
            value * value for value, is_enabled in zip(bands, enabled) if is_enabled
        )
        filter_gain = math.sqrt(selected_energy / total_energy) if total_energy > 1e-9 else 0.0
        level *= filter_gain
        peak *= filter_gain
        bands = [value if enabled[index] else 0.0 for index, value in enumerate(bands)]
        self._music_phase += dt
        ctx = self._music_beat.update(
            time.monotonic(), self._take_music_onsets(web_audio["active"]),
            bands, level, dt, self.music_beat_lead_ms / 1000.0,
        )
        self._music_ctx = ctx
        # Each pattern shows kick, snare and downbeat in its own way; there is no
        # shared full-strip tint, which made every hit look the same.
        self._draw_music_animation(frame, level, peak, dt, bands)

    def _take_music_onsets(self, web_active):
        """Kick/snare onsets from the active microphone, honouring the selected bands
        (kick needs a bass band, snare a mid or high band)."""
        sources = (self.web_mics, self.audio_input)
        active = self.web_mics if web_active else self.audio_input
        samples = []
        for source in sources:
            if source is None:
                continue
            taken = source.take_onsets()
            if source is active:
                samples = taken
        enabled = self.music_enabled_bands
        allowed = {
            "kick": enabled[0] or enabled[1],
            "snare": enabled[3] or enabled[4] or enabled[5],
        }
        return [sample for sample in samples if allowed[sample[1]]]

    def _draw_christmas_glitter(self, frame, level, peak):
        """Show slow candy-cane blocks, then a brief multicolor glitter burst."""
        palette = (
            (0, 255, 50), (0, 180, 255), (255, 190, 0),
            (210, 0, 255), (255, 40, 90), (0, 255, 210),
        )
        ctx = self._music_ctx
        # Bursts land every N beats counted from a downbeat, once the grid is locked.
        counted = ctx.bar_in_section * 4 + ctx.beat_in_bar
        glitter_phase = (
            ctx.locked and counted % self.music_glitter_every_beats == 0 and ctx.phase < 0.24
        )
        if glitter_phase:
            # Burst brightness is independently calibrated in Admin settings.
            frame.brightness_override = self.music_glitter_brightness
        beat = min(1.0, ctx.pulse)
        stripe_shift = int(ctx.beat / 2.0)
        bass = min(1.0, max(ctx.bands[0], ctx.bands[1] * 0.88) * 2.5)
        base_brightness = min(1.0, 0.26 + level * 0.22 + bass * 0.3 + beat * 0.55)
        glitter_brightness = min(1.0, 0.72 + level * 0.2 + peak * 0.08)
        glitter_tick = int(ctx.t * 18.0)

        for index in range(frame.count):
            if glitter_phase:
                seed = ((index * 73) ^ (glitter_tick * 193) ^
                        (index * glitter_tick * 17)) % 100
                color = palette[(index * 7 + glitter_tick * 3 + seed // 10) % len(palette)]
                factor = glitter_brightness * (0.72 + (seed % 28) / 100.0)
            else:
                stripe = ((index + stripe_shift) // 5) % 2
                color = (235, 8, 22) if stripe == 0 else (255, 245, 230)
                factor = base_brightness
                if stripe:   # the snare lights the white stripes
                    factor = min(1.0, factor + 0.4 * ctx.snare_pulse)
            frame.set(index, tuple(int(channel * factor) for channel in color))

    def _draw_music_animation(self, frame, level, peak, dt=0.0, bands=None):
        count = self.count
        if not count:
            return
        if self.music_animation == "live_band":
            self._draw_live_band(frame, bands or [level] * 6, dt)
            return
        if self.music_animation == "bpm_trace":
            frame.clear()
            ctx = self._music_ctx
            if ctx.locked:
                self._bpm_trace_position = (ctx.phase * count) % count
                attack = min(1.0, ctx.pulse * 4.0)
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
            pulse = self._music_ctx.pulse
            speed = 38.0 + level * 5.0 + pulse * 2.0
            self._kitt_position += self._kitt_direction * speed * max(0.0, dt)
            if self._kitt_position >= count - 1:
                self._kitt_position = count - 1
                self._kitt_direction = -1.0
            elif self._kitt_position <= 0:
                self._kitt_position = 0.0
                self._kitt_direction = 1.0
            head = int(round(self._kitt_position))
            transient = max(pulse, self._music_ctx.snare_pulse * 0.8,
                            max(0.0, peak - level * 0.62) * 3.2)
            self._kitt_speak = max(transient, self._kitt_speak * math.exp(-max(0.0, dt) * 13.0))
            for offset in range(-3, 4):
                index = head + offset
                if not 0 <= index < count:
                    continue
                strength = max(0.0, 1.0 - abs(offset) / 4.0)
                strength = strength * strength
                # Pure KITT red. Bass beat pulses drive a quick flash followed
                # by a near-dark gap, while the scanner keeps sweeping.
                pulse_brightness = 0.035 + 0.965 * self._kitt_speak
                red = int(255 * strength * pulse_brightness)
                frame.set(index, (red, 0, 0))
            return
        if self.music_animation == "laser_dance":
            self._draw_laser_dance(frame, bands or [level] * 6, dt)
            return
        if self.music_animation == "christmas_glitter":
            self._draw_christmas_glitter(frame, level, peak)
            return
        if self.music_animation in BEAT_PATTERNS:
            # Sparse shapes need the low/mid range expanded to stay visible at
            # ordinary listening levels.
            level = min(1.0, (level * 1.5) ** 0.82)
            peak = min(1.0, (peak * 1.5) ** 0.82)
            frame.clear()
            if self.music_animation == "inward_diamonds":
                self._draw_inward_diamonds(frame, level, peak, dt)
            else:
                getattr(self, "_draw_" + self.music_animation)(frame, level, dt)
            return
        if self.music_animation == "red_shades":
            bass = max(bands[0], bands[1] * 0.88) if bands else level
            bass = min(1.0, (bass * 1.7) ** 0.72)
            ctx = self._music_ctx
            beat = min(1.0, ctx.pulse)
            fast_beat_pulse = None
            if ctx.locked and ctx.period <= 0.5:
                pulse_width = 0.38
                fast_beat_pulse = 1.0 - ctx.phase / pulse_width if ctx.phase < pulse_width else 0.0
            for index in range(count):
                wave = (math.sin(index * 0.48 + self._music_phase * 4.0) + 1.0) * 0.5
                # Bass energy carries the steady pulse, while onset/predicted
                # beat energy adds a clear kick without requiring RMS volume
                # to change much across the track.
                if fast_beat_pulse is not None:
                    # At fast tempos, reserve most of each beat for a dark
                    # gap so adjacent flashes remain visually distinct.
                    pulse = fast_beat_pulse
                    red = int(max(0, min(
                        255, pulse * (24 + bass * 112 + wave * (24 + 82 * bass) + peak * 8),
                    )))
                else:
                    red = int(max(8, min(
                        255,
                        10 + bass * 92 + wave * (18 + 100 * bass) + beat * 110 + peak * 12,
                    )))
                red = min(255, int(red * (1.0 + 0.4 * ctx.downbeat_pulse)))
                frame.set(index, (red, 0, 0))
            self._snare_ends(frame, (255, 0, 0))
            return

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
