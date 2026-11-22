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
# leaks into a techno show. "club" is red, black and white with one fixed meaning per
# sound (see techno.py); "neon" is colorful (cyan, magenta, acid green). ``roles`` lists, per section role, the layers (track, preset) to run; a drop
# alternates between its two variants every 16-bar phrase.
LOOKS = {
    "club": {
        "palettes": {},
        "presets": {
            "field_low": {"pattern": "field", "level": 0.10},
            "field_mid": {"pattern": "field", "level": 0.15},
            "field_high": {"pattern": "field", "level": 0.25},
            "field_breathe": {"pattern": "field", "level": 0.32, "breathe": True},
            "pulse_soft": {"pattern": "pulse", "gain": 0.55},
            "pulse": {"pattern": "pulse"},
            "pulse_heavy": {"pattern": "pulse", "heavy": True},
            "accents": {"pattern": "accents"},
            "countdown": {"pattern": "countdown"},
            "shutdown": {"pattern": "shutdown"},
            "lead": {"pattern": "lead", "core": "#FF5050"},
            "lead_soft": {"pattern": "lead", "core": "#FF5050", "gain": 0.6},
        },
        "roles": {
            "intro": [[("base", "field_low"), ("fx", "pulse_soft"), ("lead", "lead")]],
            "breakdown": [[("base", "field_breathe"), ("lead", "lead_soft")]],
            "build": [[("base", "countdown")]],
            "outro": [[("base", "shutdown")]],
            "drop": [[("base", "field_mid"), ("fx", "pulse"), ("flash", "accents"), ("lead", "lead")],
                     [("base", "field_high"), ("fx", "pulse_heavy"), ("flash", "accents"), ("lead", "lead")]],
        },
        "comet": None,
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
            "lead": {"pattern": "lead", "color": "#FF2EA6", "core": "#FFFFFF"},
        },
        "roles": {
            "intro": [[("base", "intro")]], "breakdown": [[("base", "breakdown")]],
            "build": [[("base", "build")]], "outro": [[("base", "outro")]],
            "drop": [[("base", "drop_neon"), ("lead", "lead")], [("base", "drop_acid"), ("lead", "lead")]],
        },
        "comet": "#00E5FF",
    },
}
DEFAULT_LOOK = "club"
TRACKS = [{"id": "base", "blend": "replace"}, {"id": "fx", "blend": "add"},
          {"id": "flash", "blend": "add"}, {"id": "lead", "blend": "add"}]


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
    """Name each stretch: ``[(name, role, variant, first_bar, bar_count)]`` (bars from 0).
    ``role`` is intro/breakdown/build/drop/outro; ``variant`` alternates for drops."""
    sections, drops, breakdowns = [], 0, 0
    for index, (state, first, length) in enumerate(runs):
        last = index == len(runs) - 1
        fades = (last and state == "drive" and index > 0 and runs[index - 1][0] == "drive"
                 and _mean(bar_levels[first:first + length])
                 < 0.7 * _mean(bar_levels[runs[index - 1][1]:first]))
        # The first stretch is the intro; a drive run was split off the second one only
        # when the intro was split from the first drop (two drive runs in a row).
        if index == 0 and (state == "low" or length <= 24 or (len(runs) > 1 and runs[1][0] == "drive")):
            sections.append(("Intro", "intro", 0, first, length))
        elif fades or (state == "low" and last):
            sections.append(("Outro", "outro", 0, first, length))
        elif state == "low":
            breakdowns += 1
            build = min(BUILD_BARS, length // 2) if length >= 8 else min(2, length // 2)
            sections.append(("Breakdown %d" % breakdowns, "breakdown", 0, first, length - build))
            if build:
                sections.append(("Build %d" % breakdowns, "build", 0, first + length - build, build))
        else:
            drops += 1
            phrase = 0
            for offset in range(0, length, LONG_DROP_BARS):
                size = min(LONG_DROP_BARS, length - offset)
                if length - offset - size < MIN_SECTION_BARS and offset + size < length:
                    size = length - offset   # fold a short tail into the last phrase
                label = "Drop %d" % drops + ("" if length <= LONG_DROP_BARS else " (%d)" % (phrase + 1))
                sections.append((label, "drop", (drops + phrase) % 2, first + offset, size))
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
    cues, markers, active = [], [], {}
    for index, (name, role, variant, first, length) in enumerate(sections):
        at = "%d|1|0" % (first + 1)
        markers.append({"at": at, "name": name})
        options = scheme["roles"][role]
        layers = dict(options[variant % len(options)])
        for track in sorted(set(active) - set(layers)):   # layers the new section does not use go dark
            cues.append({"at": at, "op": "stop", "track": track})
        for track, preset in layers.items():
            if active.get(track) == preset and role != "build":
                continue   # the same layer carries on, keeping its bar count and state
            cue = {"at": 0.0 if index == 0 else at, "op": "go", "track": track, "preset": preset}
            if role in ("build", "drop"):
                cue["cut"] = True
            if preset in ("countdown", "shutdown", "build"):
                cue.update({"beats": length * BEATS_PER_BAR, "bars": length})
            cues.append(cue)
        active = layers
        if scheme["comet"] and role in ("intro", "breakdown") and length >= 4:
            cues.append({"at": at, "op": "fire", "track": "fx", "pattern": "comet", "dir": "up",
                         "speed": 26, "tail": 7, "color": scheme["comet"], "every": "4bar",
                         "until": "%d|1|0" % (first + length + 1)})
    return {
        "format": "ledcue", "version": 1, "song": song,
        "time": {"ppq": 480, "tempo_map": [
            {"at": round(first_bar_time, 4), "bpm": bpm, "beats_per_bar": BEATS_PER_BAR}]},
        "palettes": scheme["palettes"],
        "tracks": TRACKS,
        "presets": scheme["presets"], "markers": markers, "cues": cues,
    }
