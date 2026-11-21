"""Player colour assignment.

Colours are distributed evenly around the hue wheel and converted to RGB so
they are visually distinct regardless of how many players join.
"""

from led.colors import hsv_to_rgb


def distribute_hues(n):
    """Return ``n`` hues (degrees) evenly spaced around the colour wheel."""
    if n <= 0:
        return []
    return [(360.0 * i / n) % 360.0 for i in range(n)]


def player_color(hue, saturation=0.9, value=1.0):
    """Convert a hue (degrees) into a player RGB colour."""
    return hsv_to_rgb(hue, saturation, value)
