"""Musical clock for moods: beat envelopes and beat-quantized motion."""

import math


def ease_out(x):
    x = max(0.0, min(1.0, x))
    return 1.0 - (1.0 - x) ** 3


class BeatContext:
    """What a mood needs to know about "now": position in the bar plus features."""

    def __init__(self):
        self.t = 0.0
        self.dt = 0.0
        self.beat = 0.0          # fractional beats since beat 0
        self.beat_index = 0
        self.phase = 0.0         # 0-1 within the current beat
        self.beat_in_bar = 0     # 0 is the downbeat; snare lands on 1 and 3
        self.new_beat = False
        self.new_eighth = False
        self.new_bar = False
        self.bar_in_section = 0
        self.progress = 0.0      # 0-1 through the section
        self.accent = 0.5        # measured onset strength of this beat
        self.offbeat_accent = 0.3
        self.bands = [0.0] * 6
        self.level = 0.0
        self.kick = 0.0
        self.snare = 0.0

    @property
    def is_downbeat(self):
        return self.beat_in_bar == 0

    @property
    def is_backbeat(self):
        return self.beat_in_bar in (1, 3)

    @property
    def hit(self):
        """Sharp envelope: 1.0 exactly on the beat, gone within ~150 ms."""
        return math.exp(-self.phase * 8.0) * (0.6 + 0.4 * self.accent)

    @property
    def offbeat_hit(self):
        """Envelope for the "and" between beats (the 8th-note upbeat)."""
        if self.phase < 0.5:
            return 0.0
        return math.exp(-(self.phase - 0.5) * 14.0) * (0.5 + 0.5 * self.offbeat_accent)

    @property
    def bar_position(self):
        """0-1 across the bar."""
        return (self.beat_in_bar + self.phase) / 4.0

    def subdivision_hit(self, per_beat, decay=7.0):
        """Envelope that fires ``per_beat`` times per beat (2 = 8ths, 4 = 16ths)."""
        return math.exp(-((self.beat * per_beat) % 1.0) * decay)

    def stepped(self, per_beat=1.0, snap=0.03):
        """Beat-quantized counter: jumps one unit per ``1/per_beat`` beat, easing
        into place over the first ``snap`` of each step so motion lands ON the beat.
        The default is effectively instant, so a jump and the beat's pop happen in the
        same frame and read as one flash rather than two."""
        position = self.beat * per_beat
        whole = math.floor(position)
        return whole + ease_out((position - whole) / snap)
