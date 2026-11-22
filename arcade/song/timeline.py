"""Musical map of the song: tempo grid and emotional sections.

Tempo and the first beat come from tools/analyze_song.py's beat tracker (the
song is a constant 150.147 BPM; a slightly slower guess drifts half a second
off by the end). Beat 0 is a downbeat: snare accents land on beats 2 and 4.
Section boundaries are bar numbers (bar 0 starts at BEAT_OFFSET) matched to
the arrangement's energy changes and repeated material.
"""

from collections import namedtuple

BPM = 150.147
BEAT = 60.0 / BPM
BAR = BEAT * 4
BEAT_OFFSET = 0.012

Section = namedtuple("Section", "name mood start_bar end_bar cut")


def bar_time(bar):
    return BEAT_OFFSET + bar * BAR


# ``cut`` sections replace the previous look instantly (build-ups and the
# chorus "drop") instead of cross-fading, so no other effect blends in.
SECTIONS = (
    Section("Sleigh bells", "bells", 0, 4, False),
    Section("Verse 1", "verse", 4, 20, False),
    Section("Rising hope", "rising", 20, 28, False),
    Section("Whisper", "whisper", 28, 32, False),
    Section("Build-up", "build", 32, 34, True),
    Section("Chorus 1", "chorus", 34, 52, True),
    Section("Verse 2", "verse_green", 52, 64, False),
    Section("Chorus 2", "chorus", 64, 80, True),
    Section("Verse 3", "rising", 80, 92, False),
    Section("Dream", "dream", 92, 106, False),
    Section("Build-up", "build_gold", 106, 108, True),
    Section("Final chorus", "chorus_gold", 108, 124, True),
    Section("Finale", "finale", 124, 136, False),
    Section("Afterglow", "afterglow", 136, 10_000, False),
)


def section_at(seconds):
    """Return ``(index, section, progress 0-1, bar within section)``."""
    bar = (seconds - BEAT_OFFSET) / BAR
    for index, section in enumerate(SECTIONS):
        if bar < section.end_bar:
            span = section.end_bar - section.start_bar
            progress = max(0.0, min(1.0, (bar - section.start_bar) / span))
            return index, section, progress, max(0, int(bar - section.start_bar))
    return len(SECTIONS) - 1, SECTIONS[-1], 1.0, 0
