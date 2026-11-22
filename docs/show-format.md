# LED show cue format ("ledcue") — design proposal

Status: **implemented (format version 1).** Loader/compiler `arcade/song/cuesheet.py`,
player `arcade/song/engine.py`, pattern library `arcade/song/patterns.py`, song
library `arcade/song/library.py`, MIDI compiler `tools/compile_show.py`, tests in
`tests/`. The bundled show is `assets/song/*.ledcue.json`. This describes a file that stores
a whole song's light show as *cues* (launch a named pattern at a timecode)
instead of baked frames, so latency can be changed without touching the file
and the Pi only does a little work per frame.

## 1. Prior art, and what we borrow

Facts below are from memory, not re-verified; check versions before depending on them.

| Existing thing | Domain | What it gives us | Use it for |
|---|---|---|---|
| **Standard MIDI File (SMF)** | music, DAWs | Tick-based timeline, tempo map, markers, notes (trigger + velocity + length), controllers (parameter automation). Editable in Reaper/Ableton/Logic next to the audio waveform. | **Authoring and interchange.** |
| **MIDI Show Control (MSC)** | theatre/stage | Standard "GO / STOP / LOAD cue N" messages. | Live triggering later (not a file format). |
| **SMPTE timecode (ST 12), LTC/MTC** | film, stage | `HH:MM:SS:FF` addressing and a sync clock; frame rates are 24/25/30 only. | Idea only: we sync to the audio position, and 40 fps is not an SMPTE rate. |
| **Lighting-console cue lists** (ETC Eos, grandMA, QLab) | stage | Cue = fade time + what changes; "tracking" vs "cue-only" state. | Cue semantics, and state reconstruction when seeking. |
| **DMX512 / Art-Net / sACN** | stage | Per-frame channel streaming. | Not a file format; it is the baked-frame extreme. |
| **xLights `.xsq`, Vixen, LOR** | holiday/LED displays | Effects placed on a timeline with parameters, per layer. | The closest model for our cue list. |
| **FSEQ + Falcon Player (FPP)** | Raspberry Pi WS281x players | Baked frames (punch card) that xLights renders for FPP. | What we avoid: it cannot adapt to latency or seek in effect terms. |
| **Skybrush / drone shows** | drone light shows | Keyframes with interpolation instead of per-frame samples; compact light programs. | Parameter automation as keyframes + easing. |
| **Fireworks cue lists** (Finale 3D-style scripts) | pyrotechnics | Fire time plus a per-effect lead time so the burst lands on the beat. | Per-pattern `lead` (anticipation) to compensate latency. |
| **EDL / OpenTimelineIO** | film editing | Tracks, clips, markers as a plain-text/JSON timeline. | Overall structure of the runtime file. |

**Recommendation: do not invent a binary format.**

1. **Author in a DAW** with the song loaded (waveform, tempo grid snapping; this
   would also replace guessing section boundaries by ear). Export a `.mid`.
2. **Compile offline** (`tools/compile_show.py`, any laptop) to a small
   **`.ledcue.json`**. JSON is stdlib-only on the Pi, diffable in git, and
   hand-editable.
3. The Pi loads the JSON once at song start and never sees MIDI.

## 2. Clocks and latency (the key design point)

Three separate delays exist; the file may only contain the first.

| Delay | Lives in | Notes |
|---|---|---|
| `audio_offset` — encoder delay / priming of this MP3 | **file header** | Intrinsic to the audio file (e.g. ~0.025 s). Authored once. |
| `audio_latency` — player start to sound leaving the speaker | **runtime setting** | Measured by the existing mic loopback tool. Changing it never edits the file. |
| `led_lead` — one rendered frame plus strip refresh | **runtime constant** | ~25–40 ms at 40 fps; 60 LEDs refresh in ~2 ms. |

```
show_time = player_wall_clock − audio_latency − audio_offset + led_lead
```

Cue times are in **song time** (what the listener hears). A cue may also carry
`lead` (seconds): the pattern starts that much early, the same trick fireworks
use, for patterns with a slow attack. Latency recalibration, auto-sync nudges,
pause and seek only change `show_time`.

## 3. File layout

```jsonc
{
  "format": "ledcue", "version": 1,
  "song": { "id": "aiwfc", "title": "All I Want for Christmas Is You",
            "audio": "all-i-want-for-christmas-is-you.mp3",
            "duration": 242.39, "audio_offset": 0.0,
            "analysis": "all-i-want-for-christmas-is-you.analysis.json" },  // optional

  "time": { "ppq": 480,
            "tempo_map": [ { "at": 0.012, "bpm": 150.147, "beats_per_bar": 4 } ] },

  "palettes": { "holly": ["#EB0C1C", "#00C83C", "#FFD696"],
                "ice":   ["#145AFF", "#3C8CFF", "#D2E6FF"] },

  "tracks": [                      // layers, bottom to top
    { "id": "base",   "blend": "replace" },
    { "id": "accent", "blend": "add" },
    { "id": "sparks", "blend": "add" }
  ],

  "presets": {                     // named parameter bundles for built-in patterns
    "verse_dots": { "pattern": "lattice", "pitch": 6, "width": 2, "step": "1b", "palette": "holly" },
    "chorus_dots": { "pattern": "lattice", "pitch": 6, "width": 3, "step": "1b", "palette": "holly" },
    "blue_riser": { "pattern": "riser", "palette": "ice", "bars": 2, "dotted": true }
  },

  "markers": [ { "at": "5|1|0", "name": "Verse 1" }, { "at": "35|1|0", "name": "Chorus 1" } ],

  "cues": [ /* see below */ ]
}
```

### Time notation

* a number is **seconds** of song time (`54.36`);
* a string `"bar|beat|tick"` is **musical** (1-based like a DAW, `ppq` ticks per
  beat) and is resolved through `tempo_map`, so a tempo fix moves every cue;
* durations: `"4b"` beats, `"2bar"`, `"0.5s"`.

### Cues

Closed vocabulary of five operations; no scripting, no `eval`.

| `op` | Meaning | Typical fields |
|---|---|---|
| `go` | Start a looping pattern on a track (replaces that track's pattern). | `track`, `preset` or `pattern`, `params`, `fade_in`, `lead` |
| `fire` | One-shot that ends itself (flash, comet, burst). | `track`, `pattern`, `dur`, `vel`, `lead` |
| `set` | Change parameters of the running pattern, optionally ramped. | `track`, `params`, `over`, `ease` |
| `stop` | Release a track with a fade. | `track`, `fade_out` |
| `seed` | Fix the random seed for sparkle-style patterns, so a seek renders the same picture. | `value` |

Repeat rules keep the file short (a whole song is a few hundred lines):
`every`, `until`/`count`, and a velocity binding to the analysis file.

```jsonc
"cues": [
  { "at": "1|1|0",  "op": "go",   "track": "base",   "pattern": "sparkle", "params": { "palette": "gold", "rate": 0.3 } },
  { "at": "5|1|0",  "op": "go",   "track": "base",   "preset": "verse_dots", "fade_in": "1b" },
  { "at": "5|1|0",  "op": "fire",  "track": "sparks", "pattern": "comet", "dir": "up",
    "every": "4bar", "until": "29|1|0" },
  { "at": "5|1|0",  "op": "fire",  "track": "accent", "pattern": "beat_pop", "every": "1b",
    "until": "29|1|0", "vel": "analysis.beat_accent" },
  { "at": "29|1|0", "op": "go",   "track": "base",   "pattern": "twinkle", "params": { "palette": "ice", "density": 0.1 } },
  { "at": "33|1|0", "op": "go",   "track": "base",   "preset": "blue_riser", "cut": true },
  { "at": "35|1|0", "op": "go",   "track": "base",   "preset": "chorus_dots", "cut": true },
  { "at": "35|1|0", "op": "fire",  "track": "accent", "pattern": "downbeat_gold", "every": "1bar", "until": "53|1|0" },
  { "at": "35|2|0", "op": "fire",  "track": "accent", "pattern": "snare_dots", "every": "2b", "until": "53|1|0" }
]
```

Field notes:

* `cut: true` skips the cross-fade (this is what separates the blue riser from
  the whisper).
* `vel` is a number 0–1 or a named analysis channel (`analysis.level`,
  `analysis.bands[0]`, `analysis.beat_accent`), so measured accents can drive
  intensity while *timing* still comes from the grid.
* Patterns are named built-ins implemented in Python (`arcade/song/patterns.py`):
  `bells`, `verse_dots` (`lively`), `whisper`, `riser` (`style`: `ice`/`gold`),
  `chorus_dots` (`accent`), `ribbons`, `finale`, `afterglow`, and the one-shot
  `comet` (`dir`, `speed`, `tail`, `color`). The file supplies parameters only.
  A `set` cue can ramp a track's `brightness` (0-1); other parameters need a
  pattern with an `update()` method.
* Unknown pattern or newer `version`: skip that cue and log it; never crash a show.

## 4. MIDI authoring map (offline only)

| MIDI element | Becomes |
|---|---|
| Tempo / time-signature meta events | `time.tempo_map` |
| Marker meta events | `markers` (sections, jump targets) |
| One MIDI track per LED track (track name = id) | `tracks` |
| Note number | pattern or preset, via a small patch sheet (`36 = verse_dots`, …) |
| Note velocity | `vel` |
| Note length | `dur` (`fire`) or the span until the next `go`/`stop` |
| Control change (CC1, CC11, …) | `set` ramps, e.g. brightness or speed |
| Program change | palette |

## 5. Runtime on the Pi 4 (design intent)

*Compile on load, not per frame:*

1. Resolve musical times to seconds via the tempo map, expand repeat rules,
   sort cues by time, pre-resolve presets and palettes to tuples of ints.
   Hundreds of cues; milliseconds.
2. Per frame (40 fps): compute `show_time`; take the cues now due with
   `bisect` (a moving index, no scanning); update the few active layers
   (roughly 3–8); each pattern is a pure function that writes pixels for
   `local_t` and its params; composite per `blend`; hand the 60-pixel frame to
   the existing output stage.
3. Output stays as today: `led/renderer.py` is the sole writer, then
   `led/hardware.py` applies hidden-LED offsets, color balance and brightness
   before `rpi_ws281x` writes to GPIO18.

Rough cost estimate (not measured): 8 layers × 60 pixels × 40 fps is about
20,000 pixel operations per second, a small fraction of one Pi 4 core, and no
per-frame allocation if buffers are reused.

*Seek, pause and resume (tracking semantics from lighting consoles):*

* State-changing cues (`go`, `set`, `stop`) are replayed up to the target time
  to rebuild each track. Precompute a snapshot at every marker so a seek
  replays only a short span.
* `fire` one-shots older than their `dur` are dropped; the rest restart at
  the right local time.
* `seed` cues make randomized patterns identical after a seek.

## 6. What it replaced

`timeline.py` (tempo, sections) and `choreography.py` (mood per section) were
constants in code; they are now one `.ledcue.json` per song. Patterns stay in
Python, and `SongSession` plays whichever song the library selects. Adding a
song is data only: drop `song.mp3` and `song.ledcue.json` (plus the analysis
JSON from `tools/analyze_song.py`) into `assets/song/`; it appears in the
picker automatically.

Author from MIDI with `python tools/compile_show.py show.mid patch.json -o
assets/song/new.ledcue.json` (stdlib only; the patch sheet format is in the
tool's docstring). Run the tests with `python -m unittest discover tests`.

## 7. Open questions

* Pattern vocabulary versioning (what a `lattice` means must not drift).
* How much audio reactivity to allow in the file versus a deterministic mode.
* Whether to ship the MIDI source beside the compiled JSON in each song folder.

## 8. Auto-generated shows (songs added through the website)

`arcade/song/showgen.py` writes an ordinary show file from an analysis: bars with
the kick playing are *drive*, bars without it are *low*. The first stretch is the
Intro, the last low stretch the Outro, middle low stretches Breakdowns (their last
bars the Build) and drive stretches after a breakdown Drops (alternating neon and
acid palettes every 16 bars). The downbeat is where the kick returns after a
breakdown. The "club" look is red, black and white only and gives each sound one fixed visual
(kick wave from the centre, snare blocks at the ends, a bar for the acid/lead line, one
full-strip flash per 8-bar phrase, a fill of rounds before the next phrase), with no
randomness and at most three large-area flashes per second. The result can be edited
like any other show file.
