"""Interactive, cross-platform SCP deployment to the Raspberry Pi.

Requires Python 3 and OpenSSH ``ssh``/``scp`` on the computer running it.
"""

import getpass
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import tempfile
import uuid


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".deploy.env"
EXCLUDED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache"}
EXCLUDED_FILES = {".deploy.env", "runtime-settings.json", "runtime-settings.json.tmp"}


def read_env_file():
    values = {}
    if not ENV_FILE.exists():
        return values
    for line_number, raw_line in enumerate(ENV_FILE.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid {ENV_FILE.name} line {line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if value.startswith(("'", '"')) and value.endswith(value[0]):
            value = value[1:-1]
        if not key.replace("_", "").isalnum() or not key:
            raise ValueError(f"Invalid environment variable name on line {line_number}")
        if "\n" in value or "\r" in value:
            raise ValueError(f"Invalid newline in {ENV_FILE.name} line {line_number}")
        values[key] = value
    return values


def ask(values, key, prompt, default=""):
    current = values.get(key) or default
    label = f"{prompt} [{current}]: " if current else f"{prompt}: "
    answer = input(label).strip()
    value = answer or current
    if not value:
        raise ValueError(f"{prompt} is required")
    return value


def build_archive(destination):
    with tarfile.open(destination, "w:gz") as archive:
        for current, dirs, files in os.walk(ROOT):
            current_path = Path(current)
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
            for filename in sorted(files):
                path = current_path / filename
                relative = path.relative_to(ROOT)
                if filename in EXCLUDED_FILES or filename.endswith((".pyc", ".pyo")):
                    continue
                archive.add(path, arcname=(Path("led-arcade") / relative).as_posix(), recursive=False)


def systemd_env_value(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main():
    values = read_env_file()
    host = ask(values, "PI_HOST", "Raspberry Pi IP or hostname")
    user = ask(values, "PI_USER", "Pi login username", "pi")
    app_dir = ask(values, "REMOTE_APP_DIR", "Remote install directory", f"/home/{user}/led-arcade")
    venv = ask(values, "REMOTE_VENV", "Python environment directory", f"/home/{user}/neopixel-env")

    secrets = {
        key: value for key, value in values.items()
        if key.startswith(("LED_ARCADE_", "LED_AUDIO_")) and value
    }
    if not secrets.get("LED_ARCADE_ADMIN_PASSWORD"):
        secrets["LED_ARCADE_ADMIN_PASSWORD"] = getpass.getpass("Website admin password (input hidden): ")
    if not secrets["LED_ARCADE_ADMIN_PASSWORD"]:
        raise ValueError("An admin password is required")

    # Paths with spaces complicate remote shell and systemd unit substitution.
    if any(" " in path for path in (app_dir, venv)):
        raise ValueError("Remote application and environment paths cannot contain spaces")

    remote = f"{user}@{host}"
    transfer_id = uuid.uuid4().hex[:12]
    archive_remote = f"/tmp/led-arcade-{transfer_id}.tar.gz"
    env_remote = f"/tmp/led-arcade-env-{transfer_id}"

    with tempfile.TemporaryDirectory(prefix="led-arcade-deploy-") as temp_dir:
        archive_local = Path(temp_dir) / "led-arcade.tar.gz"
        env_local = Path(temp_dir) / "led-arcade.env"
        build_archive(archive_local)
        env_local.write_text(
            "".join(f"{key}={systemd_env_value(value)}\n" for key, value in sorted(secrets.items())),
            encoding="utf-8",
        )
        os.chmod(env_local, 0o600)

        print(f"Copying project to {remote} (SSH may prompt for your Pi password).")
        subprocess.run(["scp", str(archive_local), f"{remote}:{archive_remote}"], check=True)
        subprocess.run(["scp", str(env_local), f"{remote}:{env_remote}"], check=True)

    remote_script = " && ".join([
        f"mkdir -p {shlex.quote(app_dir)}",
        f"tar -xzf {shlex.quote(archive_remote)} -C {shlex.quote(app_dir)} --strip-components=1",
        f"chmod 600 {shlex.quote(env_remote)}",
        f"sudo install -o root -g root -m 600 {shlex.quote(env_remote)} /etc/led-arcade.env",
        f"rm -f {shlex.quote(archive_remote)} {shlex.quote(env_remote)}",
        "sudo env "
        f"APP_DIR={shlex.quote(app_dir)} VENV={shlex.quote(venv)} "
        f"bash {shlex.quote(app_dir + '/deploy/install.sh')}",
    ])
    print("Installing and restarting the arcade service on the Pi.")
    subprocess.run(["ssh", "-tt", remote, remote_script], check=True)
    print(f"\nDeployment complete: http://{host}:5000")
    print(f"Check status with: ssh {remote} sudo systemctl status led-arcade")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"Deployment failed: {exc}")
