"""Live patterns that speak one visual language for the music's rhythm.

Every pattern here reads the live ``BeatContext`` (``self._music_ctx``) and
keeps the same meaning for each sound, so the rhythm is readable at a glance:

* **downbeat** (beat 1 of the bar) - the biggest change: colors swap or the
  shape starts over, at most once per bar;
* **kick / beat** - a pop of brightness or a step of motion on the main shape;
* **snare** (beats 2 and 4) - the blocks at both ends of the strip flash in the
  accent color, a place the kick never uses;
* **loudness** - only a slow envelope that sets the overall size.

Until the beat grid locks, kicks and snares come straight from the detected
hits, and shapes move freely.
"""

import math

from arcade.music_colors import blend_rgb as _blend_rgb
from arcade.song.effects import add, scaled
from arcade.song.techno import Accents, Field, Lead, Pulse
from led.colors import hsv_to_rgb

END_BLOCK = 5            # pixels at each end that flash on the snare
SNARE_TINT = 0.75        # snare blocks lean this far from accent toward white


def _follow(current, target, dt, attack=14.0, release=3.0):
    """Exponential follower: fast toward louder, slow back down."""
    rate = attack if target > current else release
    return current + (target - current) * (1.0 - math.exp(-max(0.0, dt) * rate))


def _soft_span(frame, center, radius, color, strength):
    """A symmetric glow around ``center`` with fractional, anti-aliased edges."""
    reach = int(math.ceil(radius)) + 1
    for pixel in range(int(center) - reach, int(center) + reach + 2):
        amount = max(0.0, min(1.0, radius + 0.5 - abs(pixel - center)))
        if amount > 0.0:
            add(frame, pixel, scaled(color, amount * strength))


class BeatPatternMixin:
    # -- shared accents ------------------------------------------------------
    def _beat_colors(self):
        """Primary and accent, swapped on every other bar once the bar is known."""
        ctx = self._music_ctx
        primary, accent = self._music_primary_rgb, self._music_accent_rgb
        if ctx.locked and ctx.bar_known and ctx.bar_in_section % 2:
            return accent, primary
        return primary, accent

    def _snare_ends(self, frame, color=None, size=END_BLOCK):
        """The snare's fixed place: both ends of the strip flash once."""
        amount = self._music_ctx.snare_pulse
        if amount < 0.02:
            return
        color = color or _blend_rgb(self._music_accent_rgb, (255, 255, 255), SNARE_TINT)
        for index in list(range(size)) + list(range(frame.count - size, frame.count)):
            add(frame, index, scaled(color, amount))

    def _music_envelope(self, name, target, dt, attack=14.0, release=3.0):
        state = self._beat_pattern_state
        state[name] = _follow(state.get(name, 0.0), target, dt, attack, release)
        return state[name]

    # -- patterns ------------------------------------------------------------
    def _draw_center_pulse(self, frame, level, dt):
        """A cool-to-warm gradient from the centre: size follows loudness, each
        beat pushes it out and brightens it, the snare lights the ends."""
        ctx = self._music_ctx
        size = self._music_envelope("center_size", level, dt)
        middle = (frame.count - 1) / 2.0
        reach = (0.25 + 0.6 * size + 0.15 * ctx.pulse) * (frame.count / 2.0)
        primary, accent = self._beat_colors()
        brightness = 0.3 + 0.35 * size + 0.35 * ctx.pulse
        for index in range(frame.count):
            distance = abs(index - middle)
            edge = max(0.0, min(1.0, reach - distance + 0.5))
            if edge <= 0.0:
                continue
            color = _blend_rgb(primary, accent, distance / max(1.0, middle))
            frame.pixels[index] = scaled(color, edge * brightness * (1.0 - 0.5 * distance / max(1.0, reach)))
        self._snare_ends(frame)

    def _draw_mirror_bars(self, frame, level, dt):
        """Three-pixel blocks mirrored from the centre that step outward one block
        per beat; loudness sets how far they reach, the snare lights the ends."""
        ctx = self._music_ctx
        size = self._music_envelope("mirror_size", level, dt)
        half = (frame.count + 1) // 2
        reach = (0.3 + 0.7 * size) * half
        step = int(ctx.stepped(1)) if ctx.locked else 0
        primary, accent = self._beat_colors()
        brightness = 0.45 + 0.25 * size + 0.3 * ctx.pulse
        for offset in range(half):
            edge = max(0.0, min(1.0, reach - offset))
            if edge <= 0.0:
                break
            block = (offset // 3 + step) % 2
            if offset % 3 == 2:          # a dark pixel between blocks keeps them readable
                continue
            color = scaled(primary if block == 0 else accent, edge * brightness)
            frame.pixels[half - 1 - offset] = color
            frame.pixels[min(frame.count - 1, half + offset)] = color
        self._snare_ends(frame)

    def _draw_comet(self, frame, level, dt):
        """One lap of the strip per bar, starting on the downbeat; beats brighten
        the tail. Without a beat grid it drifts at a loudness-led speed."""
        ctx = self._music_ctx
        state = self._beat_pattern_state
        size = self._music_envelope("comet_size", level, dt)
        if ctx.locked:
            head = ctx.bar_position * frame.count
        else:
            head = (state.get("comet_head", 0.0) + max(0.0, dt) * (8.0 + 18.0 * size)) % frame.count
        state["comet_head"] = head
        tail = 6 + int(10 * size)
        primary, accent = self._beat_colors()
        strength = 0.4 + 0.3 * size + 0.3 * ctx.pulse
        for offset in range(tail):
            index = int(head - offset) % frame.count
            fade = (1.0 - offset / tail) ** 1.5
            color = _blend_rgb(primary, accent, offset / max(1, tail - 1))
            add(frame, index, scaled(color, fade * strength))
        self._snare_ends(frame)

    def _draw_rainbow_wave(self, frame, level, dt):
        """A rainbow drifting along the strip; each beat brightens it, each
        downbeat turns the hues a quarter of the way round."""
        ctx = self._music_ctx
        state = self._beat_pattern_state
        if ctx.new_bar and ctx.locked:
            state["rainbow_turn"] = state.get("rainbow_turn", 0.0) + 90.0
        turn = state.get("rainbow_turn", 0.0)
        drift = self._music_phase * 25.0
        size = self._music_envelope("rainbow_size", level, dt)
        brightness = min(1.0, 0.22 + 0.3 * size + 0.45 * ctx.pulse)
        for index in range(frame.count):
            hue = (index * 360.0 / frame.count + drift + turn) % 360.0
            frame.pixels[index] = hsv_to_rgb(hue, 1.0, brightness)
        self._snare_ends(frame, (255, 255, 255))

    def _draw_inward_diamonds(self, frame, level, peak, dt):
        """Diamonds launched from both ends on the downbeat meet in the centre at
        the end of the bar; each beat makes them flare, the snare whitens their core."""
        ctx = self._music_ctx
        state = self._beat_pattern_state
        size = self._music_envelope("diamond_level", level, dt)
        spread = self._music_envelope("diamond_peak", peak, dt, 10.0, 2.0)
        half = (frame.count - 1) / 2.0
        if ctx.locked:
            travel = ctx.bar_position * half
        else:
            travel = (state.get("diamond_travel", 0.0) + max(0.0, dt) * (6.0 + 12.0 * size)) % half
        state["diamond_travel"] = travel
        radius = 2.0 + 3.0 * min(1.0, spread) + 2.0 * ctx.pulse
        brightness = 0.4 + 0.3 * size + 0.3 * ctx.pulse
        primary, accent = self._beat_colors()
        _soft_span(frame, travel, radius, primary, brightness)
        _soft_span(frame, frame.count - 1 - travel, radius, accent, brightness)
        if ctx.snare_pulse > 0.02:
            white = scaled((255, 255, 255), ctx.snare_pulse * 0.8)
            for center in (travel, frame.count - 1 - travel):
                add(frame, int(round(center)), white)

    def _draw_club(self, frame, level, dt):
        """The song shows' club look, live: the kick wave from the centre, snare
        blocks at both ends, the lead bar, and a phrase flash every 8 bars."""
        ctx = self._music_ctx
        layers = self._beat_pattern_state.setdefault(
            "club", {"field": Field(0.15, breathe=True), "pulse": Pulse(),
                     "accents": Accents(), "lead": Lead()},
        )
        layers["field"].render(frame, ctx)
        if ctx.locked:
            layers["pulse"].render(frame, ctx)
            layers["accents"].render(frame, ctx)
        else:
            middle = (frame.count - 1) / 2.0
            _soft_span(frame, middle, 1.0 + 4.0 * ctx.kick_hit, (255, 0, 0), ctx.kick_hit)
            self._snare_ends(frame, (255, 0, 0), 7)
        layers["lead"].render(frame, ctx)
