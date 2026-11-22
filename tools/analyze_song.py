"""Offline analysis for a song show (development tool); the app does the same on upload.

Writes ``<song>.analysis.json`` next to the MP3. Needs numpy plus mpg123, ffmpeg
or macOS afconvert for decoding:

    python tools/analyze_song.py assets/song/all-i-want-for-christmas-is-you.mp3
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcade.song.analyzer import analyze_file  # noqa: E402


def main():
    source = Path(sys.argv[1])
    with tempfile.TemporaryDirectory() as tmp:
        data = analyze_file(source, tmp, lambda fraction, stage: print("%3d%% %s" % (fraction * 100, stage)))
    out = source.with_suffix(".analysis.json")
    out.write_text(json.dumps(data, separators=(",", ":")))
    print("Tempo %.3f BPM, first beat at %.3f s" % (data["tempo"]["bpm"], data["tempo"]["offset"]))
    print("Wrote", out, "-", data["frames"], "frames,", data["duration"], "s")


if __name__ == "__main__":
    main()
