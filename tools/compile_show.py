"""Compile a DAW-authored MIDI file into a ``.ledcue.json`` show (offline tool).

Author the show in any DAW with the song loaded: markers name the sections,
one MIDI track per LED track, notes launch patterns (see the patch sheet), and
control changes ramp parameters. Needs only the Python standard library:

    python tools/compile_show.py show.mid patch.json -o assets/song/my-song.ledcue.json

The patch sheet is JSON with the show's ``song`` header, ``first_beat`` (seconds
of beat 1 in the audio), ``palettes``/``tracks``/``presets`` copied into the
output, ``notes`` (MIDI note number -> cue fields such as ``{"op": "go",
"preset": "chorus"}``) and optional ``cc`` (controller number -> ``{"param":
"brightness"}``). See docs/show-format.md section 4.
"""

import argparse
import json
import struct
import sys


def _varlen(data, pos):
    value = 0
    while True:
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, pos


def parse_midi(data):
    """Return ``(ppq, [track events])``; events are ``(tick, kind, a, b)`` tuples.

    Kinds: ``tempo`` (microseconds per beat), ``timesig`` (numerator), ``marker``
    (text), ``name`` (text), ``on``/``off`` (note, velocity), ``cc`` (number, value).
    """
    if data[:4] != b"MThd":
        raise ValueError("not a MIDI file")
    _, ntracks, division = struct.unpack(">HHH", data[8:14])
    if division & 0x8000:
        raise ValueError("SMPTE-time MIDI files are not supported; use ticks per quarter note")
    pos, tracks = 14, []
    for _ in range(ntracks):
        if data[pos:pos + 4] != b"MTrk":
            raise ValueError("corrupt MIDI track header")
        length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        end, pos = pos + 8 + length, pos + 8
        events, tick, status = [], 0, 0
        while pos < end:
            delta, pos = _varlen(data, pos)
            tick += delta
            byte = data[pos]
            if byte == 0xFF:  # meta event
                kind, pos = data[pos + 1], pos + 2
                size, pos = _varlen(data, pos)
                payload, pos = data[pos:pos + size], pos + size
                if kind == 0x51:
                    events.append((tick, "tempo", int.from_bytes(payload, "big"), 0))
                elif kind == 0x58:
                    events.append((tick, "timesig", payload[0], 0))
                elif kind in (0x06, 0x07):
                    events.append((tick, "marker", payload.decode("utf-8", "replace"), 0))
                elif kind == 0x03:
                    events.append((tick, "name", payload.decode("utf-8", "replace"), 0))
                continue
            if byte in (0xF0, 0xF7):  # sysex: skip
                size, pos = _varlen(data, pos + 1)
                pos += size
                continue
            if byte & 0x80:
                status, pos = byte, pos + 1
            kind = status & 0xF0
            first = data[pos]
            if kind in (0xC0, 0xD0):
                pos += 1
                continue
            second = data[pos + 1]
            pos += 2
            if kind == 0x90 and second > 0:
                events.append((tick, "on", first, second))
            elif kind in (0x80, 0x90):
                events.append((tick, "off", first, 0))
            elif kind == 0xB0:
                events.append((tick, "cc", first, second))
        tracks.append(events)
    return division, tracks


def _musical(tick, ppq, beats_per_bar):
    beat_ticks = ppq * beats_per_bar
    return "%d|%d|%d" % (tick // beat_ticks + 1, tick % beat_ticks // ppq + 1, tick % ppq)


def _beats(ticks, ppq):
    return "%sb" % ("%.4f" % (ticks / ppq)).rstrip("0").rstrip(".")


def compile_midi(data, patch):
    """Build the ledcue dictionary from MIDI bytes and a patch sheet."""
    ppq, tracks = parse_midi(data)
    first_beat = float(patch.get("first_beat", 0.0))
    events = [event for track in tracks for event in track]
    bars = next((e[2] for e in sorted(events) if e[1] == "timesig"), patch.get("beats_per_bar", 4))

    tempo_map, seconds, last_tick, microseconds = [], first_beat, 0, None
    for tick, _, value, _ in sorted(e for e in events if e[1] == "tempo"):
        if microseconds is not None:
            seconds += (tick - last_tick) / ppq * microseconds / 1e6
        tempo_map.append({"at": round(seconds, 4), "bpm": round(60e6 / value, 4), "beats_per_bar": bars})
        last_tick, microseconds = tick, value
    if not tempo_map:
        tempo_map = [{"at": first_beat, "bpm": float(patch.get("bpm", 120)), "beats_per_bar": bars}]

    markers = [{"at": _musical(tick, ppq, bars), "name": text}
               for tick, kind, text, _ in sorted(e for e in events if e[1] == "marker")]
    track_map = patch.get("track_map", {})
    notes, controllers, cues, warnings = patch.get("notes", {}), patch.get("cc", {}), [], []
    for track in tracks:
        name = next((e[2] for e in track if e[1] == "name"), "")
        track_id = track_map.get(name, name)
        open_notes = {}
        for tick, kind, a, b in track:
            if kind == "on":
                open_notes[a] = (tick, b)
            elif kind == "off" and a in open_notes:
                start, velocity = open_notes.pop(a)
                spec = notes.get(str(a))
                if spec is None:
                    warnings.append("note %d on track %r has no entry in the patch sheet" % (a, name))
                    continue
                cue = dict(spec, at=_musical(start, ppq, bars), track=track_id)
                if cue.get("op") == "fire":
                    cue.setdefault("dur", _beats(tick - start, ppq))
                    cue["vel"] = round(velocity / 127.0, 3)
                cues.append((start, cue))
                if cue.get("op") == "go" and spec.get("stop_at_end"):
                    cue.pop("stop_at_end")
                    cues.append((tick, {"at": _musical(tick, ppq, bars), "op": "stop", "track": track_id}))
            elif kind == "cc" and str(a) in controllers:
                spec = controllers[str(a)]
                cue = {"at": _musical(tick, ppq, bars), "op": "set", "track": track_id,
                       "params": {spec["param"]: round(b / 127.0, 3)}}
                if "over" in spec:
                    cue["over"] = spec["over"]
                cues.append((tick, cue))
    cues.sort(key=lambda item: item[0])

    show = {"format": "ledcue", "version": 1, "song": patch["song"],
            "time": {"ppq": ppq, "tempo_map": tempo_map}}
    for key in ("palettes", "tracks", "presets"):
        if key in patch:
            show[key] = patch[key]
    show["markers"], show["cues"] = markers, [cue for _, cue in cues]
    return show, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("midi")
    parser.add_argument("patch")
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args()
    with open(args.midi, "rb") as midi_file, open(args.patch, encoding="utf-8") as patch_file:
        show, warnings = compile_midi(midi_file.read(), json.load(patch_file))
    with open(args.output, "w", encoding="utf-8") as out:
        json.dump(show, out, indent=1)
        out.write("\n")
    for warning in warnings:
        print("warning:", warning, file=sys.stderr)
    print("Wrote %s: %d cues, %d markers" % (args.output, len(show["cues"]), len(show["markers"])))


if __name__ == "__main__":
    main()
