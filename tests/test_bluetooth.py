"""Tests for the Bluetooth pairing window: python -m unittest discover tests"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from web.bluetooth import BluetoothPairing, BluetoothUnavailable, parse_devices  # noqa: E402

try:
    from flask import Flask
except ImportError:  # web dependencies are only on the Pi / a full dev setup
    Flask = None

PHONE = "AA:BB:CC:DD:EE:FF"


class FakeBluetoothctl:
    def __init__(self, connected="", paired=""):
        self.connected, self.paired, self.calls = connected, paired, []

    def __call__(self, *args):
        self.calls.append(args)
        if args == ("devices", "Connected"):
            return self.connected
        return self.paired if args == ("devices", "Paired") else ""


class ParseDevicesTests(unittest.TestCase):
    def test_reads_address_and_name(self):
        self.assertEqual(parse_devices(f"Device {PHONE} Dani's phone\nnoise\n"), [(PHONE, "Dani's phone")])


class StartPairingTests(unittest.TestCase):
    def test_kicks_connected_device_then_opens_window(self):
        fake = FakeBluetoothctl(f"Device {PHONE} Phone\n")
        kicked = BluetoothPairing(fake, unblock=lambda: None).start_pairing(90)
        self.assertEqual(kicked, ["Phone"])
        calls = fake.calls
        self.assertLess(calls.index(("disconnect", PHONE)), calls.index(("discoverable", "on")))
        self.assertIn(("remove", PHONE), calls)
        self.assertIn(("discoverable-timeout", "90"), calls)

    def test_unblocks_radio_before_powering_on(self):
        order = []
        pairing = BluetoothPairing(lambda *args: order.append(args) or "", unblock=lambda: order.append("unblock"))
        pairing.start_pairing(60)
        self.assertLess(order.index("unblock"), order.index(("power", "on")))

    def test_nobody_connected_just_opens_window(self):
        fake = FakeBluetoothctl()
        self.assertEqual(BluetoothPairing(fake, unblock=lambda: None).start_pairing(120), [])
        self.assertIn(("discoverable", "on"), fake.calls)
        self.assertFalse([call for call in fake.calls if call[0] in ("disconnect", "remove")])


class ForgetAllTests(unittest.TestCase):
    def test_removes_every_paired_device(self):
        fake = FakeBluetoothctl(paired=f"Device {PHONE} Phone\nDevice 11:22:33:44:55:66 Speaker\n")
        forgotten = BluetoothPairing(fake, unblock=lambda: None).forget_all()
        self.assertEqual(forgotten, ["Phone", "Speaker"])
        self.assertIn(("remove", PHONE), fake.calls)
        self.assertIn(("remove", "11:22:33:44:55:66"), fake.calls)

    def test_nothing_paired_changes_nothing(self):
        fake = FakeBluetoothctl()
        self.assertEqual(BluetoothPairing(fake, unblock=lambda: None).forget_all(), [])
        self.assertFalse([call for call in fake.calls if call[0] == "remove"])


@unittest.skipIf(Flask is None, "Flask is not installed")
class RouteTests(unittest.TestCase):
    def client(self, pairing):
        from web.bluetooth_api import register_bluetooth_routes
        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test"
        register_bluetooth_routes(app, pairing)
        return app.test_client()

    def test_rejects_unauthenticated_requests(self):
        fake = FakeBluetoothctl()
        response = self.client(BluetoothPairing(fake)).post("/api/admin/bluetooth/discoverable")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(fake.calls, [])

    def test_admin_opens_window(self):
        fake = FakeBluetoothctl(f"Device {PHONE} Phone\n")
        client = self.client(BluetoothPairing(fake))
        with client.session_transaction() as session:
            session["is_admin"] = True
        body = client.post("/api/admin/bluetooth/discoverable").get_json()
        self.assertEqual((body["ok"], body["kicked"]), (True, ["Phone"]))

    def test_reset_requires_admin(self):
        fake = FakeBluetoothctl(paired=f"Device {PHONE} Phone\n")
        response = self.client(BluetoothPairing(fake)).post("/api/admin/bluetooth/reset")
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(("remove", PHONE), fake.calls)

    def test_admin_resets_pairings(self):
        fake = FakeBluetoothctl(paired=f"Device {PHONE} Phone\n")
        client = self.client(BluetoothPairing(fake))
        with client.session_transaction() as session:
            session["is_admin"] = True
        self.assertEqual(client.post("/api/admin/bluetooth/reset").get_json()["forgotten"], ["Phone"])

    def test_missing_bluetooth_is_503(self):
        class Broken:
            def start_pairing(self, seconds):
                raise BluetoothUnavailable("Bluetooth is not installed on the Pi.")
        client = self.client(Broken())
        with client.session_transaction() as session:
            session["is_admin"] = True
        self.assertEqual(client.post("/api/admin/bluetooth/discoverable").status_code, 503)


if __name__ == "__main__":
    unittest.main()
