"""The song library: every ``*.ledcue.json`` under assets/song (bundled) and the
upload directory (songs added through the website) is a playable song."""

import json
from dataclasses import dataclass
from pathlib import Path

from arcade.song.analysis import SongAnalysis
from arcade.song.cuesheet import CueSheet, load_cuesheet
from config import SONG_UPLOAD_DIR

SONG_DIR = Path(__file__).resolve().parents[2] / "assets" / "song"
USER_SONG_DIR = Path(SONG_UPLOAD_DIR)
SHOW_SUFFIX = ".ledcue.json"


@dataclass
class LoadedSong:
    id: str
    title: str
    audio_path: Path
    sheet: CueSheet
    analysis: SongAnalysis


def _directories(directories):
    return [Path(d) for d in (directories if directories is not None else (SONG_DIR, USER_SONG_DIR))]


def list_songs(directories=None):
    """``[{"id", "title", "artist", "user", "path"}]`` for every show file, sorted by title.
    ``user`` is True for songs added through the website (those can be deleted)."""
    songs = []
    for directory in _directories(directories):
        for path in sorted(directory.glob("**/*" + SHOW_SUFFIX)):
            try:
                song = json.loads(path.read_text(encoding="utf-8"))["song"]
                songs.append({"id": song["id"], "title": song.get("title", song["id"]),
                              "artist": song.get("artist", ""), "path": path,
                              "user": directory == USER_SONG_DIR})
            except (OSError, ValueError, KeyError):
                continue
    return sorted(songs, key=lambda entry: entry["title"].lower())


def load_song(song_id=None, directories=None):
    """Load a song by id (the first one when ``song_id`` is None); None if unknown."""
    for entry in list_songs(directories):
        if song_id in (None, entry["id"]):
            sheet = load_cuesheet(entry["path"])
            folder = entry["path"].parent
            analysis = SongAnalysis(folder / sheet.song["analysis"])
            return LoadedSong(entry["id"], entry["title"], folder / sheet.song["audio"], sheet, analysis)
    return None
