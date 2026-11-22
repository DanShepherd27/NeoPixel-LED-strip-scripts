"""The song library: every ``*.ledcue.json`` in assets/song is a playable song."""

import json
from dataclasses import dataclass
from pathlib import Path

from arcade.song.analysis import SongAnalysis
from arcade.song.cuesheet import CueSheet, load_cuesheet

SONG_DIR = Path(__file__).resolve().parents[2] / "assets" / "song"
SHOW_SUFFIX = ".ledcue.json"


@dataclass
class LoadedSong:
    id: str
    title: str
    audio_path: Path
    sheet: CueSheet
    analysis: SongAnalysis


def list_songs(directory=SONG_DIR):
    """``[{"id", "title", "artist"}]`` for every show file, sorted by title."""
    songs = []
    for path in Path(directory).glob("*" + SHOW_SUFFIX):
        try:
            song = json.loads(path.read_text(encoding="utf-8"))["song"]
            songs.append({"id": song["id"], "title": song.get("title", song["id"]),
                          "artist": song.get("artist", ""), "path": path})
        except (OSError, ValueError, KeyError):
            continue
    return sorted(songs, key=lambda entry: entry["title"].lower())


def load_song(song_id=None, directory=SONG_DIR):
    """Load a song by id (the first one when ``song_id`` is None); None if unknown."""
    for entry in list_songs(directory):
        if song_id in (None, entry["id"]):
            sheet = load_cuesheet(entry["path"])
            folder = entry["path"].parent
            analysis = SongAnalysis(folder / sheet.song["analysis"])
            return LoadedSong(entry["id"], entry["title"], folder / sheet.song["audio"], sheet, analysis)
    return None
