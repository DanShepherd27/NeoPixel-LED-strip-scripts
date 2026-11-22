"""Free music mode and browser microphone routes."""

from flask import jsonify, request


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
        ):
            return jsonify({"ok": False, "message": "Microphone lease is no longer active."}), 409
        return jsonify({"ok": True})

