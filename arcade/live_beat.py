"""Live beat tracking for the microphone visualizer.

Turns kick/snare onset samples (timestamped with when the sound happened) into
the same ``BeatContext`` the song light shows use, so live patterns can ask
"is this the downbeat?", "is this a snare beat?" and "where am I in the beat?".

* **Onsets** - a kick or snare counts as a hit when it stands clearly above its
  recent average.
* **Tempo** - autocorrelation of a 50 Hz onset envelope over the last 8 s, with
  parabolic interpolation between lags (so 128 BPM is not rounded to 120 or 133)
  and a gentle preference for common tempos to settle octave ambiguity.
* **Phase** - a beat counter that runs at the tempo and is pulled toward each
  detected hit (a phase-locked loop), instead of restarting at every bass note.
* **Bar** - kick and snare strength is collected per beat of the bar; the
  downbeat is where kicks land and snares do not, the backbeats where snares do.

Hits are backdated by the measured microphone/network latency, so the beat grid
lives in "sound time"; the context shown to patterns runs slightly ahead of it
to make up for the LED output delay plus the admin's beat-sync trim.
"""

import collections
import math

from arcade.song.rhythm import BeatContext

ENVELOPE_RATE = 50                 # onset envelope bins per second
HISTORY_SECONDS = 8.0
TEMPO_RANGE_BPM = (70.0, 180.0)
TEMPO_PRIOR_BPM = 120.0            # octave ambiguity leans toward common tempos
DEFAULT_PERIOD = 0.5
OUTPUT_DELAY = 0.025               # renderer frame + LED write
LOST_AFTER = 4.0                   # seconds without hits before the lock drops
FORGET_AFTER = 10.0                # ... and before the tempo is forgotten
REFRACTORY = {"kick": 0.18, "snare": 0.12}
HIT_DECAY = {"kick": 9.0, "snare": 12.0}   # envelope fall per second


class LiveBeatContext(BeatContext):
    """``BeatContext`` plus what live patterns need on top of a song's grid."""

    def __init__(self):
        super().__init__()
        self.locked = False          # True once the grid follows the music
        self.bar_known = False       # True once the downbeat is settled
        self.backbeat_known = False  # True once snares are seen on beats 2 and 4
        self.period = DEFAULT_PERIOD
        self.kick_hit = 0.0          # envelope of the last detected kick
        self.snare_hit = 0.0         # envelope of the last detected snare
        self.new_kick = False        # a kick was detected this frame
        self.new_snare = False       # a snare was detected this frame

    @property
    def bpm(self):
        return 60.0 / self.period

    @property
    def pulse(self):
        """One pop per beat: the predicted beat when locked, else detected kicks."""
        return self.hit if self.locked else self.kick_hit

    @property
    def snare_pulse(self):
        """The snare: on predicted backbeats once they are known, else detected."""
        if self.locked and self.backbeat_known:
            return self.hit if self.is_backbeat else 0.0
        return self.snare_hit

    @property
    def beat_event(self):
        """True in the frame a beat starts (predicted when locked, else a kick)."""
        return self.new_beat if self.locked else self.new_kick

    @property
    def snare_event(self):
        """True in the frame a snare lands (a predicted backbeat once known)."""
        if self.locked and self.backbeat_known:
            return self.new_beat and self.is_backbeat
        return self.new_snare

    @property
    def downbeat_pulse(self):
        """Only on beat 1 of a settled bar; zero otherwise."""
        if self.locked and self.bar_known and self.is_downbeat:
            return self.hit
        return 0.0


class _OnsetDetector:
    """Hit when a strength sample clears its recent average by a margin."""

    def __init__(self, name):
        self.name = name
        self.average = 0.2
        self.last_time = -math.inf

    def feed(self, time, strength):
        is_hit = (strength >= max(0.45, self.average + 0.3)
                  and time - self.last_time >= REFRACTORY[self.name])
        self.average += (strength - self.average) * 0.05
        if is_hit:
            self.last_time = time
        return is_hit


class LiveBeatTracker:
    def __init__(self):
        self.ctx = LiveBeatContext()
        self._detectors = {name: _OnsetDetector(name) for name in REFRACTORY}
        self._envelope = collections.deque(maxlen=int(HISTORY_SECONDS * ENVELOPE_RATE))
        self._envelope_end = None          # bin index one past the newest bin
        self._period = None
        self._candidate = None
        self._candidate_hits = 0
        self._tempo_clock = 0.0
        self._tempo_strength = 0.0
        self._alignment = 0.0              # share of recent kicks on the grid
        self._beat = 0.0                   # beat counter in sound time ...
        self._beat_time = None             # ... valid at this monotonic time
        self._last_hit = None
        self._last_detect = {"kick": -math.inf, "snare": -math.inf}
        self._slots = {"kick": [0.0] * 4, "snare": [0.0] * 4}
        self._bar_offset = 0
        self._last_index = None
        self._last_eighth = None
        self._bar_count = 0

    # -- public ------------------------------------------------------------
    def update(self, now, samples, bands, level, dt, trim_seconds=0.0):
        """Advance to monotonic time ``now`` with new ``(time, name, strength)``
        onset samples and return the context for this frame."""
        self._advance(now)
        for time, name, strength in sorted(samples):
            self._add_to_envelope(time, name, strength)
            if self._detectors[name].feed(time, strength):
                self._on_hit(now, time, name, strength)
        self._tempo_clock += dt
        if self._tempo_clock >= 0.5:
            self._tempo_clock = 0.0
            self._update_tempo()
        self._check_silence(now)
        return self._fill_context(now, bands, level, dt, trim_seconds)

    # -- beat counter --------------------------------------------------------
    @property
    def period(self):
        return self._period or DEFAULT_PERIOD

    def _advance(self, now):
        if self._beat_time is not None:
            self._beat += (now - self._beat_time) / self.period
        self._beat_time = now

    def _beat_at(self, time):
        return self._beat - (self._beat_time - time) / self.period

    def _on_hit(self, now, time, name, strength):
        self._last_hit = time
        self._last_detect[name] = now
        beat = self._beat_at(time)
        nearest = round(beat)
        error = beat - nearest
        if name == "kick" and not self.ctx.locked:
            # Free-running: snap the grid onto each kick so the first locked
            # beats already land on them.
            self._beat -= error
            error = 0.0
        if abs(error) < 0.3:
            gain = (0.25 if name == "kick" else 0.12) * (0.5 + 0.5 * strength)
            self._beat -= error * gain
            if self._period is not None:
                self._period = min(self._max_period(), max(
                    self._min_period(), self._period * (1.0 + error * 0.015)))
        if name == "kick":
            self._alignment += ((1.0 if abs(error) < 0.15 else 0.0) - self._alignment) * 0.15
        if abs(error) < 0.2:
            self._add_to_slot(name, int(nearest) % 4, strength)
            if name == "kick":
                self.ctx.accent = strength

    # -- bar ------------------------------------------------------------------
    def _add_to_slot(self, name, slot, strength):
        for key in self._slots:
            self._slots[key] = [value * 0.97 for value in self._slots[key]]
        self._slots[name][slot] += strength

    def _bar_scores(self):
        kick, snare = self._slots["kick"], self._slots["snare"]
        scores = []
        for offset in range(4):
            def k(beat):
                return kick[(offset + beat) % 4]

            def s(beat):
                return snare[(offset + beat) % 4]
            scores.append(k(0) + 0.5 * k(2) - 0.5 * (k(1) + k(3))
                          + s(1) + s(3) - s(0) - s(2))
        return scores

    def _update_bar(self):
        scores = self._bar_scores()
        best = max(range(4), key=scores.__getitem__)
        current = scores[self._bar_offset]
        if best != self._bar_offset and scores[best] > current + max(0.5, abs(current) * 0.2):
            self._bar_offset = best
        snare = self._slots["snare"]
        off = self._bar_offset
        on_backbeats = snare[(off + 1) % 4] + snare[(off + 3) % 4]
        on_strong = snare[off] + snare[(off + 2) % 4]
        self.ctx.backbeat_known = on_backbeats >= 2.0 and on_backbeats > 2.0 * on_strong
        self.ctx.bar_known = sum(self._slots["kick"]) >= 3.0 and scores[off] > 1.0

    # -- tempo ----------------------------------------------------------------
    @staticmethod
    def _min_period():
        return 60.0 / TEMPO_RANGE_BPM[1]

    @staticmethod
    def _max_period():
        return 60.0 / TEMPO_RANGE_BPM[0]

    def _add_to_envelope(self, time, name, strength):
        weight = 1.0 if name == "kick" else 0.6
        value = max(0.0, strength - 0.5 * self._detectors[name].average) * weight
        index = int(time * ENVELOPE_RATE)
        if self._envelope_end is None:
            self._envelope_end = index
        if index >= self._envelope_end:
            gap = min(index - self._envelope_end + 1, self._envelope.maxlen)
            self._envelope.extend([0.0] * gap)
            self._envelope_end = index + 1
        position = len(self._envelope) - (self._envelope_end - index)
        if 0 <= position < len(self._envelope):
            self._envelope[position] = max(self._envelope[position], value)

    def _update_tempo(self):
        estimate = estimate_period(list(self._envelope))
        if estimate is None:
            self._tempo_strength *= 0.8
            return
        period, strength = estimate
        self._tempo_strength += (strength - self._tempo_strength) * 0.3
        if strength < 0.1:
            return
        current = self._period
        if current is None:
            self._period = period
            return
        ratio = period / current
        if 0.95 <= ratio <= 1.05:
            self._period = current + (period - current) * 0.25
            self._candidate, self._candidate_hits = None, 0
            return
        # A different tempo (often an octave or a 3:2 alias of the same beat)
        # must win several estimates in a row before the grid switches.
        if self._candidate is not None and abs(period / self._candidate - 1.0) <= 0.05:
            self._candidate_hits += 1
        else:
            self._candidate, self._candidate_hits = period, 1
        if self._candidate_hits >= 4:
            self._period = period
            self._candidate, self._candidate_hits = None, 0

    def _check_silence(self, now):
        if self._last_hit is None:
            return
        quiet = now - self._last_hit
        if quiet > FORGET_AFTER:
            self._period = None
            self._alignment = 0.0
            self._slots = {"kick": [0.0] * 4, "snare": [0.0] * 4}

    def _is_locked(self, now):
        if self._period is None or self._last_hit is None:
            return False
        if now - self._last_hit > LOST_AFTER:
            return False
        threshold = 0.35 if self.ctx.locked else 0.5   # hysteresis
        return self._alignment >= threshold and self._tempo_strength >= 0.1

    # -- output ---------------------------------------------------------------
    def _fill_context(self, now, bands, level, dt, trim_seconds):
        ctx = self.ctx
        ctx.locked = self._is_locked(now)
        ctx.period = self.period
        beat = self._beat + (OUTPUT_DELAY + trim_seconds) / self.period
        index = math.floor(beat)
        eighth = math.floor(beat * 2)
        ctx.new_beat = self._last_index is not None and index != self._last_index
        ctx.new_eighth = self._last_eighth is not None and eighth != self._last_eighth
        self._last_index, self._last_eighth = index, eighth
        if ctx.new_beat:
            self._update_bar()
        ctx.t, ctx.dt = now, dt
        ctx.beat, ctx.beat_index, ctx.phase = beat, index, beat - index
        ctx.beat_in_bar = (index - self._bar_offset) % 4
        ctx.new_bar = ctx.new_beat and ctx.beat_in_bar == 0
        if ctx.new_bar:
            self._bar_count += 1
        ctx.bar_in_section = self._bar_count
        ctx.bands, ctx.level = list(bands), level
        ctx.new_kick = self._last_detect["kick"] == now
        ctx.new_snare = self._last_detect["snare"] == now
        ctx.kick_hit = math.exp(-(now - self._last_detect["kick"]) * HIT_DECAY["kick"])
        ctx.snare_hit = math.exp(-(now - self._last_detect["snare"]) * HIT_DECAY["snare"])
        ctx.kick, ctx.snare = ctx.kick_hit, ctx.snare_hit
        return ctx


def estimate_period(envelope):
    """``(period seconds, strength 0-1)`` of the strongest beat-like repetition
    in a 50 Hz onset envelope, or None without enough signal."""
    if len(envelope) < 3 * ENVELOPE_RATE:
        return None
    # A short triangle blur lets a beat that falls between bins correlate as
    # strongly as one that lands on them, so neither tempo octave is favoured.
    kernel = (0.25, 0.5, 1.0, 0.5, 0.25)
    last = len(envelope) - 1
    blurred = [
        sum(weight * envelope[min(last, max(0, i + k - 2))] for k, weight in enumerate(kernel))
        for i in range(len(envelope))
    ]
    mean = sum(blurred) / len(blurred)
    values = [value - mean for value in blurred]
    energy = sum(value * value for value in values)
    if energy < 1e-6:
        return None

    def correlation(lag):
        if lag >= len(values):
            return 0.0
        overlap = len(values) - lag
        total = sum(values[i] * values[i - lag] for i in range(lag, len(values)))
        return total / overlap * len(values) / energy

    low = int(60.0 / TEMPO_RANGE_BPM[1] * ENVELOPE_RATE)
    high = int(math.ceil(60.0 / TEMPO_RANGE_BPM[0] * ENVELOPE_RATE))
    raw = {lag: correlation(lag) for lag in range(low - 1, high + 2)}
    scores = {}
    for lag in range(low, high + 1):
        # A true beat also repeats at twice its period; weight toward common tempos.
        doubled = correlation(lag * 2) if lag * 2 < len(values) else 0.0
        bpm = 60.0 / (lag / ENVELOPE_RATE)
        prior = math.exp(-0.5 * (math.log2(bpm / TEMPO_PRIOR_BPM) / 0.9) ** 2)
        scores[lag] = (raw[lag] + 0.5 * doubled) * (0.6 + 0.4 * prior)
    best = max(scores, key=scores.get)
    if raw[best] <= 0.0:
        return None
    # Parabolic interpolation between neighbouring lags for sub-bin precision.
    before, here, after = raw[best - 1], raw[best], raw[best + 1]
    curve = before - 2.0 * here + after
    shift = 0.5 * (before - after) / curve if curve < 0 else 0.0
    lag = best + max(-0.5, min(0.5, shift))
    return lag / ENVELOPE_RATE, max(0.0, min(1.0, here))
