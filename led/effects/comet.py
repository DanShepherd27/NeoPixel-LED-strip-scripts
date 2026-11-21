"""A bright comet head travelling the strip with a fading tail."""

from led.colors import hsv_to_rgb


class Comet:
    def __init__(self, count):
        self.count = count
        self.position = 0.0
        self.direction = 1
        self.speed = 40.0        # LEDs per second
        self.hue = 0.0
        self.hue_speed = 90.0    # hue rotation degrees/second
        self.tail_length = 8

    def render(self, frame, dt):
        self.position += self.direction * self.speed * dt
        self.hue = (self.hue + self.hue_speed * dt) % 360.0

        # Bounce at the ends.
        if self.position >= self.count - 1:
            self.position = self.count - 1
            self.direction = -1
        elif self.position <= 0:
            self.position = 0
            self.direction = 1

        head = int(round(self.position))
        for offset in range(self.tail_length):
            idx = head - self.direction * offset
            if 0 <= idx < self.count:
                # Head is bright; the tail fades to black.
                alpha = max(0.0, 1.0 - offset / self.tail_length)
                frame.blend(idx, hsv_to_rgb(self.hue, 0.8, 1.0), alpha)
