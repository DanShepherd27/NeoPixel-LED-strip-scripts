"""Register local HTTP controls and the Socket.IO compatibility API.

The server owns game state and scoring; browser clients send intents only.
Admin settings, music controls, and socket handlers live in focused modules.
"""

from flask import request, jsonify
from flask_socketio import SocketIO
from web.socket_api import register_socket_handlers

from config import MAX_NAME_LENGTH
from web.admin import register_admin_routes
from web.music_api import register_music_routes

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
    register_admin_routes(app, manager, hardware)
    register_music_routes(app, manager)

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

    register_socket_handlers(socketio, manager, _sanitize_name)

    return socketio
