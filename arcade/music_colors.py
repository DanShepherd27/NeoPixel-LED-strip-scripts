"""Color interpolation shared by music visualizer patterns."""


def blend_rgb(start, end, amount):
    amount = max(0.0, min(1.0, amount))
    return tuple(int(round(a + (b - a) * amount)) for a, b in zip(start, end))
