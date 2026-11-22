"""Admin authentication and runtime settings routes."""

import hmac
import logging
import re

from flask import jsonify, request, session

from config import ADMIN_PASSWORD, LED_COUNT
from web.runtime_settings import update_runtime_settings

log = logging.getLogger("web.admin")


def register_admin_routes(app, manager, hardware):
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
            "mic_handoff_seconds": manager.web_mics.handoff_seconds,
            "music_animation": manager.music_animation,
            "music_sensitivity": manager.music_sensitivity,
            "music_sound_profile": manager.music_sound_profile,
            "music_glitter_brightness": manager.music_glitter_brightness,
            "music_glitter_every_beats": manager.music_glitter_every_beats,
            "music_beat_lead_ms": manager.music_beat_lead_ms,
            "music_primary_color": manager.music_primary_color,
            "music_accent_color": manager.music_accent_color,
            "music_band_colors": list(manager.music_band_colors),
            "led_color_red": hardware.color_balance[0],
            "led_color_green": hardware.color_balance[1],
            "led_color_blue": hardware.color_balance[2],
            "led_brightness": hardware.brightness,
            "preview_invert_order": getattr(manager, "preview_invert_order", False),
            "song_audio_latency_ms": manager.song_audio_latency_ms,
            "song_auto_sync": manager.song_auto_sync,
        })

    @app.put("/api/admin/settings")
    def update_admin_settings():
        if not session.get("is_admin"):
            return jsonify({"ok": False, "message": "Admin login required."}), 401
        data = request.get_json(silent=True) or {}
        start_value = data.get("hidden_start")
        end_value = data.get("hidden_end")
        handoff_value = data.get("mic_handoff_seconds", manager.web_mics.handoff_seconds)
        animation_value = data.get("music_animation", manager.music_animation)
        sensitivity_value = data.get("music_sensitivity", manager.music_sensitivity)
        sound_profile = data.get("music_sound_profile", manager.music_sound_profile)
        glitter_brightness = data.get("music_glitter_brightness", manager.music_glitter_brightness)
        glitter_every_beats = data.get("music_glitter_every_beats", manager.music_glitter_every_beats)
        beat_lead_value = data.get("music_beat_lead_ms", manager.music_beat_lead_ms)
        primary_color = data.get("music_primary_color", manager.music_primary_color)
        accent_color = data.get("music_accent_color", manager.music_accent_color)
        band_colors = data.get("music_band_colors", manager.music_band_colors)
        color_red = data.get("led_color_red", hardware.color_balance[0])
        color_green = data.get("led_color_green", hardware.color_balance[1])
        color_blue = data.get("led_color_blue", hardware.color_balance[2])
        brightness = data.get("led_brightness", hardware.brightness)
        preview_invert_order = data.get("preview_invert_order", getattr(manager, "preview_invert_order", False))
        song_latency = data.get("song_audio_latency_ms", manager.song_audio_latency_ms)
        song_auto_sync = data.get("song_auto_sync", manager.song_auto_sync)
        if type(start_value) is not int or type(end_value) is not int or type(handoff_value) is not int:
            return jsonify({"ok": False, "message": "Enter whole numbers for offsets and microphone handoff."}), 400
        if type(beat_lead_value) is not int or not -100 <= beat_lead_value <= 200:
            return jsonify({"ok": False, "message": "Beat sync timing must be between -100 and 200 milliseconds."}), 400
        if any(type(value) is not int for value in (color_red, color_green, color_blue)):
            return jsonify({"ok": False, "message": "LED color balance values must be whole percentages."}), 400
        if type(song_latency) is not int or not 0 <= song_latency <= 1500:
            return jsonify({"ok": False, "message": "Song audio latency must be between 0 and 1500 milliseconds."}), 400
        if type(song_auto_sync) is not bool:
            return jsonify({"ok": False, "message": "Song auto-sync must be true or false."}), 400
        if type(brightness) is not int or not 0 <= brightness <= 255:
            return jsonify({"ok": False, "message": "LED brightness must be a whole value from 0 to 255."}), 400
        if type(preview_invert_order) is not bool:
            return jsonify({"ok": False, "message": "LED order inversion must be true or false."}), 400
        if any(not 0 <= value <= 200 for value in (color_red, color_green, color_blue)):
            return jsonify({"ok": False, "message": "LED color balance must be between 0 and 200 percent."}), 400
        if not isinstance(animation_value, str) or type(sensitivity_value) not in (int, float):
            return jsonify({"ok": False, "message": "Choose a music animation and numeric sensitivity."}), 400
        start, end = start_value, end_value
        if start < 0 or end < 0 or start + end > LED_COUNT:
            return jsonify({"ok": False, "message": "Offsets must be nonnegative and total no more than the strip length."}), 400
        if not 15 <= handoff_value <= 1800:
            return jsonify({"ok": False, "message": "Microphone handoff must be between 15 and 1800 seconds."}), 400
        if animation_value not in (
            "center_pulse", "mirror_bars", "rainbow_wave", "comet",
            "retro_vu", "inward_diamonds", "red_shades", "live_band", "bpm_trace", "laser_dance", "kitt_scanner", "christmas_glitter",
        ):
            return jsonify({"ok": False, "message": "Choose one of the available music animations."}), 400
        sensitivity = float(sensitivity_value)
        if not 0.25 <= sensitivity <= 4.0:
            return jsonify({"ok": False, "message": "Music sensitivity must be between 0.25 and 4.0."}), 400
        if sound_profile not in ("balanced", "small_speakers", "bass_forward"):
            return jsonify({"ok": False, "message": "Choose a supported speaker profile."}), 400
        if type(glitter_brightness) is not int or not 0 <= glitter_brightness <= 255:
            return jsonify({"ok": False, "message": "Glitter burst brightness must be a whole value from 0 to 255."}), 400
        if type(glitter_every_beats) is not int or glitter_every_beats not in (2, 4, 8, 16, 32):
            return jsonify({"ok": False, "message": "Choose a glitter burst interval of 2, 4, 8, 16, or 32 beats."}), 400
        if not all(isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color)
                   for color in (primary_color, accent_color)):
            return jsonify({"ok": False, "message": "Choose valid primary and accent colors."}), 400
        if (not isinstance(band_colors, list) or len(band_colors) != 6 or
                not all(isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color)
                        for color in band_colors)):
            return jsonify({"ok": False, "message": "Choose valid colors for all six frequency bands."}), 400

        try:
            update_runtime_settings({
                "hidden_start": start,
                "hidden_end": end,
                "mic_handoff_seconds": handoff_value,
                "music_animation": animation_value,
                "music_sensitivity": sensitivity,
                "music_sound_profile": sound_profile,
                "music_glitter_brightness": glitter_brightness,
                "music_glitter_every_beats": glitter_every_beats,
                "music_beat_lead_ms": beat_lead_value,
                "music_primary_color": primary_color.upper(),
                "music_accent_color": accent_color.upper(),
                "music_band_colors": [color.upper() for color in band_colors],
                "led_color_red": color_red,
                "led_color_green": color_green,
                "led_color_blue": color_blue,
                "led_brightness": brightness,
                "preview_invert_order": preview_invert_order,
                "song_audio_latency_ms": song_latency,
                "song_auto_sync": song_auto_sync,
            })
        except OSError:
            return jsonify({"ok": False, "message": "Could not save settings on the server."}), 500

        hardware.set_hidden_offsets(start, end)
        hardware.set_color_balance(color_red, color_green, color_blue)
        hardware.set_brightness(brightness)
        manager.web_mics.handoff_seconds = handoff_value
        manager.set_music_visualizer(
            animation_value, sensitivity, primary_color, accent_color,
            band_colors=band_colors,
        )
        manager.music_sound_profile = sound_profile
        manager.music_glitter_brightness = glitter_brightness
        manager.music_glitter_every_beats = glitter_every_beats
        manager.music_beat_lead_ms = beat_lead_value
        manager.preview_invert_order = preview_invert_order
        manager.song_audio_latency_ms = song_latency
        manager.song_auto_sync = song_auto_sync
        return jsonify({
            "ok": True, "hidden_start": start, "hidden_end": end,
            "mic_handoff_seconds": handoff_value,
            "music_animation": animation_value,
            "music_sensitivity": sensitivity,
            "music_sound_profile": sound_profile,
            "music_glitter_brightness": glitter_brightness,
            "music_glitter_every_beats": glitter_every_beats,
            "music_beat_lead_ms": beat_lead_value,
            "music_primary_color": manager.music_primary_color,
            "music_accent_color": manager.music_accent_color,
            "music_band_colors": list(manager.music_band_colors),
            "led_color_red": color_red,
            "led_color_green": color_green,
            "led_color_blue": color_blue,
            "led_brightness": brightness,
            "preview_invert_order": preview_invert_order,
            "song_audio_latency_ms": song_latency,
            "song_auto_sync": song_auto_sync,
        })

