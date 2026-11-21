"""A 1D RGB frame: an array of ``count`` pixels used by the renderer.

Games and effects write into a :class:`Frame` and the central renderer turns
it into physical NeoPixel output. This keeps game logic completely separate
from hardware.
"""


class Frame:
    def __init__(self, count):
        self.count = count
        self.pixels = [(0, 0, 0)] * count

    def clear(self):
        self.pixels = [(0, 0, 0)] * self.count

    def fill(self, color):
        self.pixels = [color] * self.count

    def set(self, index, color):
        if 0 <= index < self.count:
            self.pixels[index] = color

    def get(self, index):
        if 0 <= index < self.count:
            return self.pixels[index]
        return (0, 0, 0)

    def blend(self, index, color, amount):
        """Alpha-blend ``color`` over the pixel at ``index`` (0.0-1.0)."""
        if 0 <= index < self.count:
            from led.colors import blend as _blend
            self.pixels[index] = _blend(self.pixels[index], color, amount)

    def dim(self, factor):
        """Scale every pixel's brightness by ``factor`` (0.0-1.0)."""
        self.pixels = [
            tuple(int(round(c * factor)) for c in p) for p in self.pixels
        ]
