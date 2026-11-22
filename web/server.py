"""Build the Flask application and Socket.IO server for the arcade."""

import logging

from flask import Flask

from web.routes import register_routes
from web.api import register_api

log = logging.getLogger("web.server")


def create_app(manager, hardware):
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    import secrets
    import os
    app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024  # song uploads
    app.config["SECRET_KEY"] = os.environ.get("LED_ARCADE_SECRET_KEY") or secrets.token_hex(32)

    register_routes(app, manager, hardware)
    socketio = register_api(app, manager, hardware)
    return app, socketio
