"""Shared colour utilities.

Effect code and player-colour assignment both need HSV<->RGB conversion and
simple blending helpers, so they live here (with no dependency on hardware or
arcade modules).
"""

import colorsys


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def hsv_to_rgb(hue, saturation=1.0, value=1.0):
    """Convert HSV to an (r, g, b) tuple of ints in 0-255.

    ``hue`` is in degrees (0-360, wraps automatically), ``saturation`` and
    ``value`` are in 0.0-1.0.
    """
    hue = hue % 360.0
    r, g, b = colorsys.hsv_to_rgb(hue / 360.0,
                                  clamp(saturation),
                                  clamp(value))
    return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))


def rgb_to_hsv(rgb):
    """Convert an (r, g, b) tuple (0-255) to (h, s, v) with h in degrees."""
    r, g, b = rgb
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return h * 360.0, s, v


def blend(a, b, amount):
    """Linear blend between two RGB tuples. ``amount`` 0.0 -> a, 1.0 -> b."""
    return tuple(int(round(a[i] + (b[i] - a[i]) * amount)) for i in range(3))


def dim(rgb, factor):
    """Scale an RGB tuple by ``factor`` (0.0-1.0)."""
    return tuple(int(round(c * factor)) for c in rgb)
