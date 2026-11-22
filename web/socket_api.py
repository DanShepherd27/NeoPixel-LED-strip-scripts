"""Socket.IO event handlers and state broadcasting."""

from flask import request
from flask_socketio import emit


def register_socket_handlers(socketio, manager, sanitize_name):
    connections = {}

    def broadcast_state():
        socketio.emit("state", manager.get_state())

    @socketio.on("connect")
    def on_connect():
        emit("connected")

    @socketio.on("join")
    def on_join(data):
        name = sanitize_name((data or {}).get("name", ""))
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

    @socketio.on("tutorial_next")
    def on_tutorial_next():
        manager.tutorial_next()
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

