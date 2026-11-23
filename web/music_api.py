"""Free music mode and browser microphone routes."""

from flask import jsonify, request, send_file, session

from arcade.song.library import list_songs, load_song


def register_music_routes(app, manager):
    @app.post("/api/music_mode")
    def http_music_mode():
        enabled = bool((request.get_json(silent=True) or {}).get("enabled"))
        if enabled and not manager.start_music_mode():
            return jsonify({
                "ok": False,
                "message": "Free music mode can only start while the arcade is idle.",
            }), 409
        if not enabled:
            manager.stop_music_mode()
        return jsonify({"ok": True, "enabled": enabled})

    @app.post("/api/song/start")
    def song_start():
        data = request.get_json(silent=True) or {}
        try:
            started = manager.start_song(
                pi_audio=data.get("pi_audio", True) is not False, song_id=data.get("song_id"),
            )
        except KeyError:
            return jsonify({"ok": False, "message": "Unknown song."}), 404
        except Exception:
            app.logger.exception("Could not start the song show")
            return jsonify({"ok": False, "message": "The Pi could not start the song show; see the service log."}), 500
        if not started:
            return jsonify({
                "ok": False,
                "message": "The song can only start while the arcade is idle.",
            }), 409
        return jsonify({"ok": True})

    @app.post("/api/song/stop")
    def song_stop():
        manager.stop_song()
        return jsonify({"ok": True})

    @app.post("/api/song/control")
    def song_control():
        data = request.get_json(silent=True) or {}
        action = data.get("action")
        position = data.get("position")
        if action not in ("pause", "resume", "seek"):
            return jsonify({"ok": False, "message": "Choose pause, resume or seek."}), 400
        if action == "seek" and (type(position) not in (int, float) or position < 0):
            return jsonify({"ok": False, "message": "Seek needs a position in seconds."}), 400
        if not manager.control_song(action, position):
            return jsonify({"ok": False, "message": "The song show is not playing."}), 409
        return jsonify({"ok": True})

    @app.post("/api/song/calibrate")
    def song_calibrate():
        if not session.get("is_admin"):
            return jsonify({"ok": False, "message": "Admin login required."}), 401
        started, message = manager.start_song_calibration()
        if not started:
            return jsonify({"ok": False, "message": message}), 409
        return jsonify({"ok": True})

    @app.get("/api/songs")
    def songs_list():
        return jsonify([{key: song[key] for key in ("id", "title", "artist", "user")} for song in list_songs()])

    @app.get("/api/songs/<song_id>/audio")
    def song_audio(song_id):
        song = load_song(song_id)
        if song is None:
            return jsonify({"ok": False, "message": "Unknown song."}), 404
        # conditional=True enables HTTP range requests so phones can seek.
        return send_file(song.audio_path, mimetype="audio/mpeg", conditional=True)

    @app.post("/api/music/visualizer")
    def set_music_visualizer():
        if manager.state.value != "music":
            return jsonify({"ok": False, "message": "Start free music mode first."}), 409
        data = request.get_json(silent=True) or {}
        animation = data.get("animation", manager.music_animation)
        primary_color = data.get("primary_color", manager.music_primary_color)
        accent_color = data.get("accent_color", manager.music_accent_color)
        enabled_bands = data.get("enabled_bands", manager.music_enabled_bands)
        band_colors = data.get("band_colors", manager.music_band_colors)
        glitter_brightness = data.get("glitter_brightness", manager.music_glitter_brightness)
        if type(glitter_brightness) is not int or not 0 <= glitter_brightness <= 255:
            return jsonify({"ok": False, "message": "Glitter burst overdrive must be from 0 to 255."}), 400
        try:
            manager.set_music_visualizer(
                animation, manager.music_sensitivity, primary_color, accent_color,
                enabled_bands, band_colors,
            )
            manager.music_glitter_brightness = glitter_brightness
        except (ValueError, TypeError) as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        return jsonify({
            "ok": True,
            "animation": manager.music_animation,
            "primary_color": manager.music_primary_color,
            "accent_color": manager.music_accent_color,
            "enabled_bands": list(manager.music_enabled_bands),
            "band_colors": list(manager.music_band_colors),
            "glitter_brightness": manager.music_glitter_brightness,
        })

    @app.post("/api/music/mic/request")
    def music_mic_request():
        if manager.state.value != "music":
            return jsonify({"ok": False, "message": "Start free music mode first."}), 409
        data = request.get_json(silent=True) or {}
        try:
            status = manager.web_mics.request(data.get("client_id"), data.get("name", "Guest"))
        except ValueError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        return jsonify({"ok": True, **status})

    @app.post("/api/music/mic/leave")
    def music_mic_leave():
        data = request.get_json(silent=True) or {}
        status = manager.web_mics.leave(data.get("client_id"), data.get("token"))
        return jsonify({"ok": True, **status})

    @app.get("/api/music/mic/state")
    def music_mic_state():
        client_id = request.args.get("client_id")
        return jsonify(manager.web_mics.status(client_id))

    @app.post("/api/music/mic/audio")
    def music_mic_audio():
        data = request.get_json(silent=True) or {}
        if manager.state.value != "music" or not manager.web_mics.update(
            data.get("token"), data.get("level"), data.get("peak"),
            data.get("clap"), data.get("bands"), data.get("latency_ms", 40),
            hits={key: data.get(key) for key in ("kick", "kick_ago_ms", "snare", "snare_ago_ms")},
        ):
            return jsonify({"ok": False, "message": "Microphone lease is no longer active."}), 409
        return jsonify({"ok": True})

