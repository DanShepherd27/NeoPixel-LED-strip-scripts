"""Every sound-reactive pattern name, in one place for validation and settings."""

from arcade.stage import LOOKS

MUSIC_ANIMATIONS = (
    "center_pulse", "mirror_bars", "rainbow_wave", "comet",
    "retro_vu", "inward_diamonds", "red_shades", "live_band", "bpm_trace",
    "laser_dance", "kitt_scanner", "christmas_glitter", "club",
) + tuple(LOOKS)
