"""Admin routes for adding and removing songs (upload, analysis progress, delete)."""

import os
import tempfile

from flask import jsonify, request, session

from arcade.song.library import USER_SONG_DIR


def register_song_routes(app, manager, jobs):
    def admin_only():
        if not session.get("is_admin"):
            return jsonify({"ok": False, "message": "Admin login required."}), 401
        return None

    @app.post("/api/songs/import")
    def song_import():
        denied = admin_only()
        if denied:
            return denied
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return jsonify({"ok": False, "message": "Choose an MP3 file."}), 400
        USER_SONG_DIR.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=USER_SONG_DIR, suffix=".upload")
        os.close(descriptor)
        try:
            upload.save(temporary)
            job = jobs.add(temporary, upload.filename, request.form.get("title", ""),
                           request.form.get("artist", ""), request.form.get("look", "club"))
        except ValueError as exc:
            os.remove(temporary)
            return jsonify({"ok": False, "message": str(exc)}), 400
        return jsonify({"ok": True, "job": job})

    @app.get("/api/songs/imports")
    def song_imports():
        return jsonify(jobs.snapshot())

    @app.post("/api/songs/<song_id>/regenerate")
    def song_regenerate(song_id):
        denied = admin_only()
        if denied:
            return denied
        playing = manager.get_state().get("song")
        if playing and playing.get("id") == song_id:
            return jsonify({"ok": False, "message": "Stop the song before rebuilding its show."}), 409
        look = (request.get_json(silent=True) or {}).get("look")
        if not jobs.regenerate(song_id, look):
            return jsonify({"ok": False, "message": "Only songs added through the website can be rebuilt."}), 404
        return jsonify({"ok": True})

    @app.delete("/api/songs/<song_id>")
    def song_delete(song_id):
        denied = admin_only()
        if denied:
            return denied
        playing = manager.get_state().get("song")
        if playing and playing.get("id") == song_id:
            return jsonify({"ok": False, "message": "Stop the song before removing it."}), 409
        if not jobs.delete(song_id):
            return jsonify({"ok": False, "message": "Only songs added through the website can be removed."}), 404
        return jsonify({"ok": True})
