"""Pattern-specific frame rendering routines for music mode."""

import math

from arcade.music_colors import blend_rgb as _blend_rgb


class MusicPatternMixin:
    def _draw_laser_dance(self, frame, bands, dt):
        """Red-led, full-strip choreography driven by musical transients."""
        frame.clear()
        count = self.count
        bands = [max(0.0, min(1.0, float(value))) for value in bands]
        enabled = [value if self.music_enabled_bands[index] else 0.0
                   for index, value in enumerate(bands)]
        ctx = self._music_ctx
        now = ctx.t
        # Kicks and snares come from the shared beat tracker: predicted beats and
        # backbeats once it is locked, detected hits until then.
        kick_hit = ctx.beat_event
        snare_hit = ctx.snare_event
        if kick_hit:
            self._laser_kick = 1.0
            self._laser_step += 1
        else:
            self._laser_kick *= math.exp(-max(0.0, dt) * 5.0)
        if snare_hit:
            self._laser_snare = 1.0
        else:
            self._laser_snare *= math.exp(-max(0.0, dt) * 8.0)

        period = self._music_ctx.period
        selected = [value for index, value in enumerate(enabled)
                    if self.music_enabled_bands[index]]
        target_energy = sum(selected) / max(1, len(selected))
        volume_jump = target_energy - self._laser_volume
        self._laser_volume += (target_energy - self._laser_volume) * min(
            1.0, max(0.0, dt) / (0.075 if target_energy > self._laser_volume else 0.34)
        )
        rate = 0.14 if target_energy > self._laser_energy else 1.45
        self._laser_energy += (target_energy - self._laser_energy) * min(1.0, max(0.0, dt) / rate)

        # A new phrase starts every two bars on the downbeat once the bar is known.
        if ctx.locked and ctx.bar_known:
            phrase_index = ctx.bar_in_section // 2
        else:
            phrase_index = int(now / period) // 8
        if phrase_index != self._laser_phrase_index:
            self._laser_phrase_index = phrase_index
            self._laser_phrase = (phrase_index + int(self._laser_energy > 0.58)) % 5
            self._laser_call_side = phrase_index % 2
            self._laser_color_index = phrase_index % 3

        # The strip stays in a saturated fire palette; white is reserved for
        # the center of a strong transient so red remains the dominant color.
        red = (255, 10, 0)
        orange = (255, 72, 0)
        ember = (170, 8, 0)
        white = (255, 190, 120)
        colors = (red, orange, ember)
        lead_color = colors[self._laser_color_index]
        answer_color = orange if lead_color == red else red
        soft_color = ember
        section = max(1, count // 4)

        if kick_hit:
            self._laser_wave = max(self._laser_wave, 1.0)
            self._laser_wave_origin = self._laser_motion
        elif volume_jump >= 0.11:
            self._laser_wave = max(self._laser_wave, min(0.9, 0.42 + volume_jump * 2.0))
            self._laser_wave_origin = self._laser_motion
        else:
            self._laser_wave = max(0.0, self._laser_wave - max(0.0, dt) * 1.7)

        # Eased kick steps provide musical motion without a beat-by-beat flash.
        paths = (
            (2, 9, 18, 29, 40, 51, 57, 48, 37, 26, 15, 6),
            (2, 7, 13, 19, 25, 31, 37, 43, 49, 55, 49, 43, 37, 31, 25, 19, 13, 7),
            (2, 5, 9, 13, 10, 6),
            (3, 6, 10, 13, 10, 6),
            (2, 8, 15, 22, 29, 36, 43, 50, 57, 50, 43, 36, 29, 22, 15, 8),
        )
        path = paths[self._laser_phrase]
        target = path[self._laser_step % len(path)]
        if self._laser_phrase in (1, 3) and self._laser_call_side:
            target = count - 1 - target
        self._laser_target = target
        ease = 0.11 if kick_hit else 0.48
        self._laser_motion += (target - self._laser_motion) * min(1.0, max(0.0, dt) / ease)
        lead = min(count - 1, max(0, int(round(self._laser_motion))))

        def paint_run(center, length, color, strength=1.0):
            start = center - (length - 1) // 2
            for offset in range(length):
                pixel = start + offset
                if 0 <= pixel < count:
                    edge = 1.0 - abs(offset - (length - 1) / 2) / max(1.0, length)
                    frame.set(pixel, tuple(int(channel * strength * (0.62 + edge * 0.38))
                                           for channel in color))

        beat_drive = max(self._laser_kick, self._laser_snare * 0.72, self._laser_energy * 0.45)
        scan_width = 2 + int(beat_drive * 4)
        self._laser_scan = (self._laser_scan + max(0.0, dt) * (9.0 + self._laser_energy * 15.0)) % count
        scan = int(self._laser_scan)
        # Every phrase has several active clumps so the whole 60-pixel strip
        # reads as a moving light sculpture rather than isolated points.
        if self._laser_phrase == 0:
            for offset, size in ((0, 5), (-13, 3), (14, 3)):
                paint_run((lead + offset) % count, size, lead_color if offset == 0 else answer_color, 0.90)
            paint_run(scan, scan_width, orange, 0.62)
        elif self._laser_phrase == 1:
            for offset, size in ((0, 4), (12, 4), (24, 2)):
                position = (lead + offset) % count
                paint_run(position, size, lead_color if offset == 0 else answer_color, 0.92)
                paint_run(count - 1 - position, size, answer_color, 0.78)
        elif self._laser_phrase == 2:
            outer = min(section - 1, max(0, lead))
            for offset, size in ((0, 5), (7, 3), (14, 2)):
                paint_run((outer + offset) % section, size, lead_color, 0.95)
                paint_run(count - 1 - ((outer + offset) % section), size, answer_color, 0.85)
        elif self._laser_phrase == 3:
            side_start = 0 if self._laser_call_side == 0 else count - section
            local = min(section - 2, max(1, lead - side_start))
            group = side_start + local
            paint_run(group, 7, lead_color)
            paint_run((group + 9) % count, 4, orange, 0.88)
            paint_run(count - 1 - group, 5, answer_color, 0.88)
            paint_run(scan, 2, red, 0.65)
        else:
            # Counter-scanning combs cross in both directions.
            paint_run(scan, 4, lead_color, 0.92)
            paint_run(count - 1 - scan, 3, answer_color, 0.9)
            for offset in (15, 30, 45):
                paint_run((scan + offset) % count, 2, orange, 0.74)

        # Kick or sudden loudness sends a bright wave away from its launch point.
        if self._laser_wave > 0.03:
            radius = int((1.0 - self._laser_wave) * (count * 0.56))
            origin = int(round(self._laser_wave_origin))
            wave_strength = self._laser_wave * (0.75 + self._laser_energy * 0.25)
            for direction in (-1, 1):
                position = (origin + direction * radius) % count
                paint_run(position, 3 if wave_strength < 0.72 else 5,
                          white if wave_strength > 0.72 else orange, wave_strength)

        mid_energy = max(enabled[2:]) if enabled[2:] else 0.0
        if self._laser_snare > 0.12:
            for offset in (-12, 0, 12):
                paint_run((lead + offset) % count, 2, white if offset == 0 else orange,
                          self._laser_snare * (0.92 if offset == 0 else 0.62))
        elif mid_energy > 0.14:
            drift = int((math.sin(now * 1.6) + 1.0) * 0.5 * (count - 1))
            paint_run(drift, 2, soft_color, min(0.58, mid_energy * 0.72))

    def _draw_live_band(self, frame, bands, dt):
        """Render six frequency bands as independent bars along the 1D strip."""
        frame.clear()
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
                color = tuple(int(channel * intensity) for channel in self._music_band_rgb[band_index])
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
