"""Bluetooth speaker pairing window, driven through BlueZ's `bluetoothctl`."""

import logging
import re
import subprocess

log = logging.getLogger("web.bluetooth")

COMMAND_TIMEOUT_SECONDS = 8
DEVICE_LINE = re.compile(r"^Device ([0-9A-F]{2}(?::[0-9A-F]{2}){5}) ?(.*)$", re.IGNORECASE)


class BluetoothUnavailable(RuntimeError):
    """BlueZ is missing, not running, or refused a command."""


def run_bluetoothctl(*args):
    """Run one `bluetoothctl` command and return its output."""
    try:
        result = subprocess.run(
            ["bluetoothctl", *args], capture_output=True, text=True,
            timeout=COMMAND_TIMEOUT_SECONDS, check=False,
        )
    except FileNotFoundError as error:
        raise BluetoothUnavailable("Bluetooth is not installed on the Pi.") from error
    except subprocess.TimeoutExpired as error:
        raise BluetoothUnavailable("Bluetooth did not answer in time.") from error
    return result.stdout


def unblock_bluetooth():
    """Clear a software block on the radio; without it BlueZ cannot power the adapter on."""
    try:
        subprocess.run(["rfkill", "unblock", "bluetooth"], capture_output=True,
                       timeout=COMMAND_TIMEOUT_SECONDS, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        log.warning("Could not run rfkill to unblock Bluetooth")


def parse_devices(output):
    """Return [(address, name)] from `bluetoothctl devices` output."""
    devices = []
    for line in output.splitlines():
        match = DEVICE_LINE.match(line.strip())
        if match:
            devices.append((match.group(1).upper(), match.group(2).strip() or match.group(1)))
    return devices


class BluetoothPairing:
    def __init__(self, run=run_bluetoothctl, unblock=unblock_bluetooth):
        self._run = run
        self._unblock = unblock

    def connected_devices(self):
        return parse_devices(self._run("devices", "Connected"))

    def paired_devices(self):
        return parse_devices(self._run("devices", "Paired"))

    def forget_all(self):
        """Disconnect and unpair every known device, e.g. to clear a pairing a phone lost.

        Returns the names of the devices that were forgotten.
        """
        forgotten = self.paired_devices()
        for address, _name in forgotten:
            self._run("disconnect", address)
            self._run("remove", address)
        log.info("Bluetooth pairings reset; removed %s", [name for _a, name in forgotten])
        return [name for _address, name in forgotten]

    def start_pairing(self, seconds):
        """Disconnect and unpair whoever is connected, then open a discoverable window.

        Returns the names of the devices that were kicked. BlueZ closes the window itself
        after `seconds`, even if this app stops.
        """
        kicked = self.connected_devices()
        for address, _name in kicked:
            # `remove` drops the bond too, so a trusted phone cannot just reconnect.
            self._run("disconnect", address)
            self._run("remove", address)
        self._unblock()
        self._run("power", "on")
        self._run("pairable", "on")
        self._run("discoverable-timeout", str(seconds))
        self._run("discoverable", "on")
        log.info("Bluetooth discoverable for %s s; removed %s", seconds, [name for _a, name in kicked])
        return [name for _address, name in kicked]
