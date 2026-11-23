"""Admin-only Bluetooth pairing route."""

from flask import jsonify, session

from config import BLUETOOTH_DISCOVERABLE_SECONDS
from web.bluetooth import BluetoothPairing, BluetoothUnavailable


def register_bluetooth_routes(app, pairing=None):
    pairing = pairing or BluetoothPairing()

    @app.post("/api/admin/bluetooth/discoverable")
    def bluetooth_discoverable():
        if not session.get("is_admin"):
            return jsonify({"ok": False, "message": "Admin login required."}), 401
        try:
            kicked = pairing.start_pairing(BLUETOOTH_DISCOVERABLE_SECONDS)
        except BluetoothUnavailable as error:
            return jsonify({"ok": False, "message": str(error)}), 503
        return jsonify({"ok": True, "seconds": BLUETOOTH_DISCOVERABLE_SECONDS, "kicked": kicked})
