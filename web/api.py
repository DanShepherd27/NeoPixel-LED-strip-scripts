"""Socket.IO real-time API.

Browsers connect here for live state and to send player actions. The server
owns all game state and scoring; clients only send intents.
"""

import logging
import hmac
import json
import os

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
        })

    @app.put("/api/admin/settings")
    def update_admin_settings():
        if not session.get("is_admin"):
            return jsonify({"ok": False, "message": "Admin login required."}), 401
        data = request.get_json(silent=True) or {}
        start_value = data.get("hidden_start")
        end_value = data.get("hidden_end")
        if type(start_value) is not int or type(end_value) is not int:
            return jsonify({"ok": False, "message": "Enter whole numbers for both offsets."}), 400
        start, end = start_value, end_value
        if start < 0 or end < 0 or start + end > LED_COUNT:
            return jsonify({"ok": False, "message": "Offsets must be nonnegative and total no more than the strip length."}), 400

        settings_path = RUNTIME_SETTINGS_FILE
        temporary_path = settings_path + ".tmp"
        try:
            with open(temporary_path, "w", encoding="utf-8") as settings_file:
                json.dump({"hidden_start": start, "hidden_end": end}, settings_file)
            os.replace(temporary_path, settings_path)
        except OSError:
            log.exception("Could not persist LED offset settings")
            try:
                os.remove(temporary_path)
            except OSError:
                pass
            return jsonify({"ok": False, "message": "Could not save settings on the server."}), 500

        hardware.set_hidden_offsets(start, end)
        return jsonify({"ok": True, "hidden_start": start, "hidden_end": end})

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
