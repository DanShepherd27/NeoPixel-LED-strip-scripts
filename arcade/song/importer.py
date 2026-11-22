"""Add a song from an MP3: analyze it, generate a show, and track progress.

``run_import`` does the work and is run in a separate, low-priority process
(``python -m arcade.song.importer``) so the LED renderer never stalls. The
web process uses :class:`ImportJobs` to start those processes one at a time
and report progress.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
from collections import deque
from pathlib import Path

from arcade.song.analysis import SongAnalysis
from arcade.song.analyzer import AnalysisError, analyze_file, mp3_info
from arcade.song.showgen import DEFAULT_LOOK, LOOKS, generate_show

MAX_JOBS_REMEMBERED = 12


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "song"


def run_import(audio_path, out_dir, song_id, title, artist, progress, look=DEFAULT_LOOK):
    """Analyze ``audio_path`` and write analysis + show files into ``out_dir``."""
    out_dir = Path(out_dir)
    audio_path = Path(audio_path)
    rate, samples_per_frame = mp3_info(audio_path)
    with tempfile.TemporaryDirectory() as tmp:
        data = analyze_file(audio_path, tmp, progress)
    analysis_name = song_id + ".analysis.json"
    (out_dir / analysis_name).write_text(json.dumps(data, separators=(",", ":")))
    progress(0.97, "Planning the light show")
    show = generate_show(SongAnalysis(out_dir / analysis_name), {
        "id": song_id, "title": title, "artist": artist, "audio": audio_path.name,
        "analysis": analysis_name, "mp3": {"sample_rate": rate, "samples_per_frame": samples_per_frame},
    }, look)
    (out_dir / (song_id + ".ledcue.json")).write_text(json.dumps(show, indent=1) + "\n")
    progress(1.0, "Done")


def main():
    audio, out_dir, song_id, title, artist = sys.argv[1:6]
    look = sys.argv[6] if len(sys.argv) > 6 else DEFAULT_LOOK
    try:
        run_import(audio, out_dir, song_id, title, artist,
                   lambda fraction, stage: print("PROGRESS %.3f %s" % (fraction, stage), flush=True), look)
        print("DONE", flush=True)
    except Exception as exc:  # report every failure through the job, with its type
        traceback.print_exc()
        print("ERROR %s: %s" % (type(exc).__name__, exc) if not isinstance(exc, AnalysisError)
              else "ERROR %s" % exc, flush=True)
        sys.exit(1)


class ImportJobs:
    """Runs imports one at a time in background processes."""

    def __init__(self, user_dir, spawn=None):
        self.user_dir = Path(user_dir)
        self._spawn = spawn or self._spawn_process
        self._jobs = []
        self._queue = []
        self._lock = threading.Lock()
        self._worker = None

    @staticmethod
    def looks_like_mp3(path):
        with open(path, "rb") as audio_file:
            head = audio_file.read(3)
        return head == b"ID3" or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)

    def add(self, uploaded_path, filename, title="", artist="", look=DEFAULT_LOOK):
        """Queue an uploaded file. Returns the job dict; raises ValueError for non-MP3 files."""
        if not self.looks_like_mp3(uploaded_path):
            raise ValueError("Only MP3 files are supported.")
        title = (title or Path(filename).stem).strip()[:80] or "Untitled"
        with self._lock:
            taken = {job["id"] for job in self._jobs}
            if self.user_dir.exists():
                taken |= {p.name for p in self.user_dir.iterdir()}
            base = slugify(title)
            song_id, n = base, 1
            while song_id in taken:
                n += 1
                song_id = "%s-%d" % (base, n)
            folder = self.user_dir / song_id
            folder.mkdir(parents=True)
            audio = folder / (song_id + ".mp3")
            shutil.move(str(uploaded_path), audio)
            job = {"id": song_id, "title": title, "artist": artist.strip()[:80],
                   "look": look if look in LOOKS else DEFAULT_LOOK,
                   "status": "queued", "progress": 0.0, "stage": "Waiting", "message": ""}
            self._jobs.append(job)
            del self._jobs[:-MAX_JOBS_REMEMBERED]
            self._queue.append((job, folder, audio))
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._work, name="song-import", daemon=True)
                self._worker.start()
            return dict(job)

    def snapshot(self):
        with self._lock:
            return [dict(job) for job in self._jobs]

    def delete(self, song_id):
        """Remove an uploaded song's files. Returns False if it is not an uploaded song."""
        folder = self.user_dir / song_id
        if not re.fullmatch(r"[a-z0-9-]+", song_id) or not folder.is_dir():
            return False
        shutil.rmtree(folder)
        with self._lock:
            self._jobs = [job for job in self._jobs if job["id"] != song_id]
        return True

    def regenerate(self, song_id, look=None):
        """Rebuild an uploaded song's show from its saved analysis (picks up generator
        improvements without uploading again). Returns False if there is no such song."""
        folder = self.user_dir / song_id
        show_path = folder / (song_id + ".ledcue.json")
        if not re.fullmatch(r"[a-z0-9-]+", song_id) or not show_path.is_file():
            return False
        old = json.loads(show_path.read_text(encoding="utf-8"))["song"]
        meta = {key: old[key] for key in ("id", "title", "artist", "audio", "analysis", "mp3") if key in old}
        show = generate_show(SongAnalysis(folder / old["analysis"]), meta,
                             look or old.get("look", DEFAULT_LOOK))
        show_path.write_text(json.dumps(show, indent=1) + "\n")
        return True

    # -- worker ------------------------------------------------------------
    def _work(self):
        while True:
            with self._lock:
                if not self._queue:
                    return
                job, folder, audio = self._queue.pop(0)
            self._set(job, status="running", stage="Starting")
            tail = deque(maxlen=4)  # last unexpected output lines, shown if the process dies
            try:
                for line in self._spawn(audio, folder, job):
                    self._handle(job, line.strip(), tail)
            except OSError as exc:
                self._set(job, status="error", message="Could not start the analysis: %s" % exc)
            if job["status"] == "running":
                detail = " | ".join(tail)
                self._set(job, status="error", message=job["message"] or detail
                          or "The analysis stopped unexpectedly.")
            if job["status"] == "error":
                shutil.rmtree(folder, ignore_errors=True)

    def _handle(self, job, line, tail):
        if line.startswith("EXIT "):
            code = int(line[5:])
            if job["status"] == "running":
                reason = "was killed (probably out of memory)" if code < 0 else "exited with code %d" % code
                tail.appendleft("The analysis %s." % reason)
        elif line.startswith("PROGRESS "):
            _, fraction, stage = line.split(" ", 2)
            self._set(job, progress=float(fraction), stage=stage)
        elif line == "DONE":
            self._set(job, status="ready", progress=1.0, stage="Ready to play")
        elif line.startswith("ERROR "):
            self._set(job, status="error", message=line[6:])
        elif line:
            tail.append(line[-160:])

    def _set(self, job, **changes):
        with self._lock:
            job.update(changes)

    def _spawn_process(self, audio, folder, job):
        process = subprocess.Popen(
            [sys.executable, "-m", "arcade.song.importer", str(audio), str(folder),
             job["id"], job["title"], job["artist"], job["look"]],
            cwd=str(Path(__file__).resolve().parents[2]), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, preexec_fn=lambda: os.nice(10),
        )
        yield from process.stdout
        yield "EXIT %d" % process.wait()


if __name__ == "__main__":
    main()
