"""Socket.IO real-time API.

Browsers connect here for live state and to send player actions. The server
owns all game state and scoring; clients only send intents.
"""

import logging
import hmac
import json
import os
import re

from flask import request, session, jsonify
from flask_socketio import SocketIO, emit

from config import MAX_NAME_LENGTH, ADMIN_PASSWORD, RUNTIME_SETTINGS_FILE, LED_COUNT

log = logging.getLogger("web.api")

# Characters we strip from player names to avoid layout/HTML abuse.
_INVALID_NAME_CHARS = '<>&"\''


def _sanitize_name(name):
    if not isinstance(name, str):
        return ""
    name = name.strip()
    for ch in _INVALID_NAME_CHARS:
        name = name.replace(ch, "")
    name = " ".join(name.split())[:MAX_NAME_LENGTH]
    return name


def register_api(app, manager, hardware):
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

    # Maps Socket.IO session id -> player id.
    connections = {}

    # HTTP polling/control fallback. It keeps the arcade usable on an isolated
    # LAN without requiring a separately hosted Socket.IO browser bundle.
    @app.post("/api/join")
    def http_join():
        name = _sanitize_name((request.get_json(silent=True) or {}).get("name", ""))
        if not name:
            return jsonify({"message": "Please enter a name."}), 400
        player = manager.join_player(name)
        manager.touch(player.id)
        return jsonify({"player_id": player.id, "player": player.to_dict()})

    @app.post("/api/rejoin")
    def http_rejoin():
        player_id = (request.get_json(silent=True) or {}).get("player_id")
        player = manager.players.get(player_id) if isinstance(player_id, str) else None
        if not player:
            return jsonify({"message": "Player session was not found. Please join again."}), 404
        manager.touch(player.id)
        return jsonify({"player_id": player.id, "player": player.to_dict()})

    @app.post("/api/leave")
    def http_leave():
        player_id = (request.get_json(silent=True) or {}).get("player_id")
        if isinstance(player_id, str):
            manager.leave_player(player_id)
        return jsonify({"ok": True})

    @app.post("/api/ready")
    def http_ready():
        data = request.get_json(silent=True) or {}
        if isinstance(data.get("player_id"), str):
            manager.set_ready(data["player_id"], bool(data.get("ready", True)))
        return jsonify({"ok": True})

    @app.post("/api/select_game")
    def http_select_game():
        manager.select_game((request.get_json(silent=True) or {}).get("slug"))
        return jsonify({"ok": True})

    @app.post("/api/start_game")
    def http_start_game():
        manager.start_game()
        return jsonify({"ok": True})

    @app.post("/api/skip_tutorial")
    def http_skip_tutorial():
        manager.skip_tutorial()
        return jsonify({"ok": True})

    @app.post("/api/rematch")
    def http_rematch():
        manager.rematch()
        return jsonify({"ok": True})

    @app.post("/api/return_to_idle")
    def http_return_to_idle():
        manager.return_to_idle()
        return jsonify({"ok": True})

    @app.post("/api/input")
    def http_input():
        data = request.get_json(silent=True) or {}
        player_id, action = data.get("player_id"), data.get("action")
        if isinstance(player_id, str) and isinstance(action, str):
            manager.touch(player_id)
            manager.handle_input(player_id, action)
        return jsonify({"ok": True})

    @app.post("/api/ping")
    def http_ping():
        player_id = (request.get_json(silent=True) or {}).get("player_id")
        if isinstance(player_id, str):
            manager.touch(player_id)
        return jsonify({"ok": True})

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
        try:
            manager.set_music_visualizer(
                animation, manager.music_sensitivity, primary_color, accent_color,
            )
        except (ValueError, TypeError) as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        return jsonify({
            "ok": True,
            "animation": manager.music_animation,
            "primary_color": manager.music_primary_color,
            "accent_color": manager.music_accent_color,
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
            data.get("clap"), data.get("bands"),
        ):
            return jsonify({"ok": False, "message": "Microphone lease is no longer active."}), 409
        return jsonify({"ok": True})

    @app.post("/api/admin/login")
    def admin_login():
        password = (request.get_json(silent=True) or {}).get("password", "")
        if not ADMIN_PASSWORD:
            return jsonify({"ok": False, "message": "Admin password is not configured on the server."}), 503
        if not isinstance(password, str) or not hmac.compare_digest(password, ADMIN_PASSWORD):
            return jsonify({"ok": False, "message": "Incorrect password."}), 401
        session["is_admin"] = True
        return jsonify({"ok": True})

    @app.post("/api/admin/logout")
    def admin_logout():
        session.pop("is_admin", None)
        return jsonify({"ok": True})

    @app.get("/api/admin/settings")
    def admin_settings():
        if not session.get("is_admin"):
            return jsonify({"ok": False, "message": "Admin login required."}), 401
        return jsonify({
            "ok": True,
            "hidden_start": hardware.hidden_start,
            "hidden_end": hardware.hidden_end,
            "led_count": LED_COUNT,
            "mic_handoff_seconds": manager.web_mics.handoff_seconds,
            "music_animation": manager.music_animation,
            "music_sensitivity": manager.music_sensitivity,
            "music_primary_color": manager.music_primary_color,
            "music_accent_color": manager.music_accent_color,
            "led_color_red": hardware.color_balance[0],
            "led_color_green": hardware.color_balance[1],
            "led_color_blue": hardware.color_balance[2],
        })

    @app.put("/api/admin/settings")
    def update_admin_settings():
        if not session.get("is_admin"):
            return jsonify({"ok": False, "message": "Admin login required."}), 401
        data = request.get_json(silent=True) or {}
        start_value = data.get("hidden_start")
        end_value = data.get("hidden_end")
        handoff_value = data.get("mic_handoff_seconds", manager.web_mics.handoff_seconds)
        animation_value = data.get("music_animation", manager.music_animation)
        sensitivity_value = data.get("music_sensitivity", manager.music_sensitivity)
        primary_color = data.get("music_primary_color", manager.music_primary_color)
        accent_color = data.get("music_accent_color", manager.music_accent_color)
        color_red = data.get("led_color_red", hardware.color_balance[0])
        color_green = data.get("led_color_green", hardware.color_balance[1])
        color_blue = data.get("led_color_blue", hardware.color_balance[2])
        if type(start_value) is not int or type(end_value) is not int or type(handoff_value) is not int:
            return jsonify({"ok": False, "message": "Enter whole numbers for offsets and microphone handoff."}), 400
        if any(type(value) is not int for value in (color_red, color_green, color_blue)):
            return jsonify({"ok": False, "message": "LED color balance values must be whole percentages."}), 400
        if any(not 0 <= value <= 200 for value in (color_red, color_green, color_blue)):
            return jsonify({"ok": False, "message": "LED color balance must be between 0 and 200 percent."}), 400
        if not isinstance(animation_value, str) or type(sensitivity_value) not in (int, float):
            return jsonify({"ok": False, "message": "Choose a music animation and numeric sensitivity."}), 400
        start, end = start_value, end_value
        if start < 0 or end < 0 or start + end > LED_COUNT:
            return jsonify({"ok": False, "message": "Offsets must be nonnegative and total no more than the strip length."}), 400
        if not 15 <= handoff_value <= 1800:
            return jsonify({"ok": False, "message": "Microphone handoff must be between 15 and 1800 seconds."}), 400
        if animation_value not in (
            "center_pulse", "mirror_bars", "rainbow_wave", "comet",
            "retro_vu", "inward_diamonds", "red_shades", "live_band",
        ):
            return jsonify({"ok": False, "message": "Choose one of the available music animations."}), 400
        sensitivity = float(sensitivity_value)
        if not 0.25 <= sensitivity <= 4.0:
            return jsonify({"ok": False, "message": "Music sensitivity must be between 0.25 and 4.0."}), 400
        if not all(isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color)
                   for color in (primary_color, accent_color)):
            return jsonify({"ok": False, "message": "Choose valid primary and accent colors."}), 400

        settings_path = RUNTIME_SETTINGS_FILE
        temporary_path = settings_path + ".tmp"
        try:
            with open(temporary_path, "w", encoding="utf-8") as settings_file:
                json.dump({
                    "hidden_start": start,
                    "hidden_end": end,
                    "mic_handoff_seconds": handoff_value,
                    "music_animation": animation_value,
                    "music_sensitivity": sensitivity,
                    "music_primary_color": primary_color.upper(),
                    "music_accent_color": accent_color.upper(),
                    "led_color_red": color_red,
                    "led_color_green": color_green,
                    "led_color_blue": color_blue,
                }, settings_file)
            os.replace(temporary_path, settings_path)
        except OSError:
            log.exception("Could not persist LED offset settings")
            try:
                os.remove(temporary_path)
            except OSError:
                pass
            return jsonify({"ok": False, "message": "Could not save settings on the server."}), 500

        hardware.set_hidden_offsets(start, end)
        hardware.set_color_balance(color_red, color_green, color_blue)
        manager.web_mics.handoff_seconds = handoff_value
        manager.set_music_visualizer(animation_value, sensitivity, primary_color, accent_color)
        return jsonify({
            "ok": True, "hidden_start": start, "hidden_end": end,
            "mic_handoff_seconds": handoff_value,
            "music_animation": animation_value,
            "music_sensitivity": sensitivity,
            "music_primary_color": manager.music_primary_color,
            "music_accent_color": manager.music_accent_color,
            "led_color_red": color_red,
            "led_color_green": color_green,
            "led_color_blue": color_blue,
        })

    def broadcast_state():
        socketio.emit("state", manager.get_state())

    @socketio.on("connect")
    def on_connect():
        emit("connected")

    @socketio.on("join")
    def on_join(data):
        name = _sanitize_name((data or {}).get("name", ""))
        if not name:
            emit("error", {"message": "Please enter a name."})
            return
        player = manager.join_player(name)
        connections[request.sid] = player.id
        manager.touch(player.id)
        emit("joined", {"player_id": player.id, "player": player.to_dict()})
        broadcast_state()

    @socketio.on("rejoin")
    def on_rejoin(data):
        # Re-attach an existing player id (e.g. after a page refresh).
        player_id = (data or {}).get("player_id")
        if player_id and manager.players.get(player_id):
            connections[request.sid] = player_id
            manager.touch(player_id)
            emit("joined", {
                "player_id": player_id,
                "player": manager.players.get(player_id).to_dict(),
            })
            broadcast_state()

    @socketio.on("leave")
    def on_leave():
        player_id = connections.pop(request.sid, None)
        if player_id:
            manager.leave_player(player_id)
            broadcast_state()

    @socketio.on("ready")
    def on_ready(data):
        player_id = connections.get(request.sid)
        if player_id:
            manager.set_ready(player_id, bool((data or {}).get("ready", True)))
            broadcast_state()

    @socketio.on("select_game")
    def on_select_game(data):
        manager.select_game((data or {}).get("slug"))
        broadcast_state()

    @socketio.on("start_game")
    def on_start_game():
        manager.start_game()
        broadcast_state()

    @socketio.on("skip_tutorial")
    def on_skip_tutorial():
        manager.skip_tutorial()
        broadcast_state()

    @socketio.on("rematch")
    def on_rematch():
        manager.rematch()
        broadcast_state()

    @socketio.on("return_to_idle")
    def on_return_to_idle():
        manager.return_to_idle()
        broadcast_state()

    @socketio.on("input")
    def on_input(data):
        player_id = connections.get(request.sid)
        if not player_id:
            return
        action = (data or {}).get("action")
        if not isinstance(action, str):
            return
        manager.touch(player_id)
        manager.handle_input(player_id, action)

    @socketio.on("ping")
    def on_ping():
        player_id = connections.get(request.sid)
        if player_id:
            manager.touch(player_id)

    @socketio.on("disconnect")
    def on_disconnect():
        player_id = connections.pop(request.sid, None)
        if player_id:
            manager.mark_disconnected(player_id)
            broadcast_state()

    def broadcaster():
        while True:
            socketio.sleep(0.1)
            broadcast_state()

    socketio.start_background_task(broadcaster)

    return socketio
