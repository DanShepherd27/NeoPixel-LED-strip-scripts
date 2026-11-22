"""Generates a show file for a dance track from its analysis (stdlib only).

Techno and house are the easy case: a steady kick gives a reliable beat grid,
and the arrangement is told by whether the kick (low-band energy) is playing.
Bars with the kick are *drive*; bars without it are *low*. From that:

* the first stretch is the **Intro** and the last low stretch the **Outro**;
* every low stretch in the middle is a **Breakdown**, and its last bars the **Build**;
* every drive stretch after a breakdown is a **Drop**.

The downbeat (which beat starts a bar) is taken from where the kick returns
after a breakdown. Everything produced is an ordinary show file, so it can be
hand-edited afterwards.
"""

import bisect

BEATS_PER_BAR = 4
DRIVE_THRESHOLD = 0.5        # share of a bar's beats with the kick playing
KICK_BEAT_LEVEL = 0.5        # low-band level (vs the loud sections) that counts as "kick on"
MIN_SECTION_BARS = 4
BUILD_BARS = 4
LONG_DROP_BARS = 16          # long drops switch palette every this many bars

# Looks for generated shows. Every accent is spelled out so no Christmas-warm default
# leaks into a techno show. "club" is monochrome (white and steel on black); "neon"
# is colorful (cyan, magenta, acid green).
LOOKS = {
    "club": {
        "palettes": {"intro": ["#8FA3C4", "#4A5A78"], "drop_a": ["#FFFFFF", "#8FA3C4"],
                     "drop_b": ["#D8E4FF", "#5F7396"], "outro": ["#FFFFFF", "#8FA3C4"]},
        "presets": {
            "intro": {"pattern": "verse_dots", "palette": "intro", "accent": "#FFFFFF", "flash": "#FFFFFF"},
            "breakdown": {"pattern": "ribbons", "color": "#8FA3C4"},
            "build": {"pattern": "riser", "style": "mono"},
            "drop_neon": {"pattern": "chorus_dots", "palette": "drop_a", "accent": "#FFFFFF",
                          "spark": "#FFFFFF", "snare": "#FFFFFF"},
            "drop_acid": {"pattern": "chorus_dots", "palette": "drop_b", "accent": "#FFFFFF",
                          "spark": "#D8E4FF", "snare": "#FFFFFF"},
            "outro": {"pattern": "afterglow", "palette": "outro"},
        },
        "comet": "#FFFFFF",
    },
    "neon": {
        "palettes": {"intro": ["#00E5FF", "#7A5CFF"], "drop_a": ["#00E5FF", "#FF2EA6", "#FFFFFF"],
                     "drop_b": ["#A6FF00", "#FF2EA6", "#00E5FF"], "outro": ["#00E5FF", "#FF2EA6", "#7A5CFF"]},
        "presets": {
            "intro": {"pattern": "verse_dots", "palette": "intro", "accent": "#FF2EA6", "flash": "#FFFFFF"},
            "breakdown": {"pattern": "ribbons"},
            "build": {"pattern": "riser", "style": "ice"},
            "drop_neon": {"pattern": "chorus_dots", "palette": "drop_a", "accent": "#FFFFFF",
                          "spark": "#00E5FF", "snare": "#FFFFFF"},
            "drop_acid": {"pattern": "chorus_dots", "palette": "drop_b", "accent": "#FFFFFF",
                          "spark": "#FF2EA6", "snare": "#FFFFFF"},
            "outro": {"pattern": "afterglow", "palette": "outro"},
        },
        "comet": "#00E5FF",
    },
}
DEFAULT_LOOK = "club"


class _Beats:
    """Per-beat features averaged from the analysis frames."""

    def __init__(self, analysis, bpm, offset):
        self.period = 60.0 / bpm
        self.offset = offset
        self.count = max(0, int((analysis.duration - offset) / self.period))
        rate = analysis.frame_rate
        self.low, self.level = [], []
        for k in range(self.count):
            first = int((offset + k * self.period) * rate)
            last = max(first + 1, int((offset + (k + 1) * self.period) * rate))
            frames = range(first, min(last, analysis.frames))
            low = [analysis.linear("sub", i) + analysis.linear("bass", i) for i in frames]
            self.low.append(sum(low) / (2 * len(low)) if low else 0.0)
            self.level.append(sum(analysis.linear("level", i) for i in frames) / max(1, len(frames)))
        loud = sorted(self.low)
        reference = loud[int(0.9 * len(loud))] if loud else 1.0
        self.kick_on = [value >= KICK_BEAT_LEVEL * reference for value in self.low]
        self.reference = reference


def _downbeat_phase(beats, analysis):
    """Which of the four beats starts a bar: where the kick returns after a gap."""
    best, phase = 0.0, None
    for k in range(8, beats.count - 8):
        before = sum(beats.kick_on[k - 8:k]) / 8.0
        after = sum(beats.kick_on[k:k + 8]) / 8.0
        if before < 0.3 and after > 0.7:
            jump = after - before + beats.low[k] / (beats.reference or 1.0)
            if jump > best:
                best, phase = jump, k % BEATS_PER_BAR
    if phase is not None:
        return phase
    scores = [0.0] * BEATS_PER_BAR   # no breakdown: favor the beat with the strongest accents
    for k in range(beats.count):
        scores[k % BEATS_PER_BAR] += analysis.beat_accent(k)[0]
    return max(range(BEATS_PER_BAR), key=scores.__getitem__)


def _bar_states(beats, phase):
    states = []
    for start in range(phase, beats.count - BEATS_PER_BAR + 1, BEATS_PER_BAR):
        window = beats.kick_on[start:start + BEATS_PER_BAR]
        states.append("drive" if sum(window) / BEATS_PER_BAR >= DRIVE_THRESHOLD else "low")
    for i in range(1, len(states) - 1):   # a one-bar blip takes its neighbours' state
        if states[i - 1] == states[i + 1] != states[i]:
            states[i] = states[i - 1]
    return states


def _runs(states):
    """``[(state, first_bar, bar_count)]`` with runs shorter than a phrase absorbed."""
    runs = []
    for bar, state in enumerate(states):
        if runs and runs[-1][0] == state:
            runs[-1][2] += 1
        else:
            runs.append([state, bar, 1])
    merged = []
    for run in runs:
        if merged and run[2] < MIN_SECTION_BARS and run is not runs[-1]:
            merged[-1][2] += run[2]
        elif merged and merged[-1][0] == run[0]:
            merged[-1][2] += run[2]
        else:
            merged.append(run)
    return merged


def _split_intro(runs, bar_levels):
    """A drive run at the very start is intro + first drop: split where energy steps up
    (or after 16 bars if no step is found and the run is long)."""
    if not runs or runs[0][0] != "drive" or runs[0][2] < 24:
        return runs
    first, length = runs[0][1], runs[0][2]
    best, split = 1.3, None
    for bar in range(4, length - 3):
        before = sum(bar_levels[first + bar - 4:first + bar]) / 4.0
        after = sum(bar_levels[first + bar:first + bar + 4]) / 4.0
        if before > 0 and after / before > best:
            best, split = after / before, bar
    split = split or (16 if length >= 32 else None)
    if split is None:
        return runs
    return [["drive", first, split], ["drive", first + split, length - split]] + runs[1:]


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def _sections(runs, bar_levels):
    """Name each stretch: ``[(name, preset, first_bar, bar_count)]`` (bars from 0)."""
    sections, drops, breakdowns = [], 0, 0
    for index, (state, first, length) in enumerate(runs):
        last = index == len(runs) - 1
        fades = (last and state == "drive" and index > 0 and runs[index - 1][0] == "drive"
                 and _mean(bar_levels[first:first + length])
                 < 0.7 * _mean(bar_levels[runs[index - 1][1]:first]))
        # The first stretch is the intro; a drive run was split off the second one only
        # when the intro was split from the first drop (two drive runs in a row).
        if index == 0 and (state == "low" or length <= 24 or (len(runs) > 1 and runs[1][0] == "drive")):
            sections.append(("Intro", "intro", first, length))
        elif fades or (state == "low" and last):
            sections.append(("Outro", "outro", first, length))
        elif state == "low":
            breakdowns += 1
            build = min(BUILD_BARS, length // 2) if length >= 8 else min(2, length // 2)
            sections.append(("Breakdown %d" % breakdowns, "breakdown", first, length - build))
            if build:
                sections.append(("Build %d" % breakdowns, "build", first + length - build, build))
        else:
            drops += 1
            preset = "drop_neon" if drops % 2 else "drop_acid"
            alternate = "drop_acid" if preset == "drop_neon" else "drop_neon"
            phrase = 0
            for offset in range(0, length, LONG_DROP_BARS):
                size = min(LONG_DROP_BARS, length - offset)
                if length - offset - size < MIN_SECTION_BARS and offset + size < length:
                    size = length - offset   # fold a short tail into the last phrase
                label = "Drop %d" % drops + ("" if length <= LONG_DROP_BARS else " (%d)" % (phrase + 1))
                sections.append((label, preset if phrase % 2 == 0 else alternate, first + offset, size))
                phrase += 1
                if offset + size >= length:
                    break
    return sections


def generate_show(analysis, meta, look=DEFAULT_LOOK):
    """Return a show dictionary for ``meta`` = id/title/artist/audio/analysis/mp3 fields.
    ``look`` picks the color scheme from LOOKS."""
    scheme = LOOKS.get(look) or LOOKS[DEFAULT_LOOK]
    look = look if look in LOOKS else DEFAULT_LOOK
    bpm, offset = analysis.tempo["bpm"], analysis.tempo["offset"]
    beats = _Beats(analysis, bpm, offset)
    phase = _downbeat_phase(beats, analysis)
    states = _bar_states(beats, phase)
    bar_levels = [_mean(beats.level[phase + b * BEATS_PER_BAR:phase + (b + 1) * BEATS_PER_BAR])
                  for b in range(len(states))]
    runs = _split_intro(_runs(states), bar_levels)
    sections = _sections(runs, bar_levels) if runs else []
    first_bar_time = offset + phase * beats.period

    song = dict(meta, duration=round(analysis.duration, 2), audio_offset=0.0,
                analysis_beat_offset=phase, look=look)
    cues, markers = [], []
    for index, (name, preset, first, length) in enumerate(sections):
        at = "%d|1|0" % (first + 1)
        markers.append({"at": at, "name": name})
        cue = {"at": 0.0 if index == 0 else at, "op": "go", "track": "base", "preset": preset}
        if preset in ("build", "drop_neon", "drop_acid"):
            cue["cut"] = True
        cues.append(cue)
        if preset in ("intro", "breakdown") and length >= 4:
            cues.append({"at": at, "op": "fire", "track": "sparks", "pattern": "comet", "dir": "up",
                         "speed": 26, "tail": 7, "color": scheme["comet"], "every": "4bar",
                         "until": "%d|1|0" % (first + length + 1)})
    return {
        "format": "ledcue", "version": 1, "song": song,
        "time": {"ppq": 480, "tempo_map": [
            {"at": round(first_bar_time, 4), "bpm": bpm, "beats_per_bar": BEATS_PER_BAR}]},
        "palettes": scheme["palettes"],
        "tracks": [{"id": "base", "blend": "replace"}, {"id": "sparks", "blend": "add"}],
        "presets": scheme["presets"], "markers": markers, "cues": cues,
    }
