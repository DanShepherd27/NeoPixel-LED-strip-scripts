"""Merge-style persistence for runtime-settings.json."""

import json
import logging
import os

from config import RUNTIME_SETTINGS_FILE

log = logging.getLogger("web.runtime_settings")


def update_runtime_settings(changes):
    """Write ``changes`` into the settings file, keeping every other saved key."""
    try:
        with open(RUNTIME_SETTINGS_FILE, "r", encoding="utf-8") as settings_file:
            settings = json.load(settings_file)
        if not isinstance(settings, dict):
            settings = {}
    except (FileNotFoundError, ValueError):
        settings = {}
    settings.update(changes)
    temporary_path = RUNTIME_SETTINGS_FILE + ".tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as settings_file:
            json.dump(settings, settings_file)
        os.replace(temporary_path, RUNTIME_SETTINGS_FILE)
    except OSError:
        log.exception("Could not persist runtime settings")
        try:
            os.remove(temporary_path)
        except OSError:
            pass
        raise
