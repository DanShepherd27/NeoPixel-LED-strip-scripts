"""HTTP routes (pages and simple REST endpoints)."""

import io

from flask import render_template, jsonify, request

from arcade.games import game_catalog


def register_routes(app, manager, hardware):
    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/state")
    def api_state():
        state = manager.get_state()
        if state.get("music_led_frame") is not None:
            state["music_led_frame"] = [
                list(pixel) for pixel in hardware.preview_colors(state["music_led_frame"])
            ]
        return jsonify(state)

    @app.route("/api/games")
    def api_games():
        return jsonify(game_catalog())

    @app.route("/healthz")
    def healthz():
        return jsonify({
            "ok": True,
            "state": manager.state.value,
            "led_hardware": "mock" if hardware.mock else "ready",
            "led_error": hardware.hardware_error,
            "led_count": hardware.count,
            "hidden_start": hardware.hidden_start,
            "hidden_end": hardware.hidden_end,
            "audio": manager.audio_input.snapshot() if manager.audio_input else None,
        })

    @app.route("/qr.svg")
    def qr_svg():
        """Serve a QR code pointing at this server so phones can join easily."""
        import qrcode
        import qrcode.image.svg
        url = "http://{host}/".format(host=request.host)
        image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage)
        buf = io.BytesIO()
        image.save(buf)
        return buf.getvalue(), 200, {"Content-Type": "image/svg+xml"}
