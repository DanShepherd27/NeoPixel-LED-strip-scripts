"""Colors and small drawing helpers shared by the moods."""

from led.colors import dim

RED = (235, 12, 28)
GREEN = (0, 200, 60)
GOLD = (255, 176, 24)
WARM = (255, 214, 150)
SNOW = (210, 230, 255)
ICE = (60, 140, 255)
WHITE_HOT = (255, 235, 200)


def scaled(color, factor):
    return dim(color, max(0.0, min(1.0, factor)))


def add(frame, index, color):
    if 0 <= index < frame.count:
        old = frame.pixels[index]
        frame.pixels[index] = tuple(min(255, old[i] + color[i]) for i in range(3))


def add_all(frame, color):
    for index in range(frame.count):
        add(frame, index, color)


def lattice(index, shift, pitch, width):
    """Group number if ``index`` is lit in a repeating pattern of ``width`` lit
    pixels then ``pitch - width`` dark ones (shifted by ``shift``), else None."""
    slot = index + shift
    if int(slot) % pitch < width:
        return int(slot) // pitch
    return None


def segment(frame, beat_in_bar):
    """The quarter of the strip that stands for this beat of the bar."""
    size = frame.count // 4
    return range(beat_in_bar * size, (beat_in_bar + 1) * size)


class Sparkles:
    """Pixels that flare then fade."""

    def __init__(self, fade_per_second=2.0):
        self.fade = fade_per_second
        self.lives = {}

    def spawn(self, index, color, life=1.0):
        self.lives[index] = (color, life)

    def draw(self, frame, dt, strength=1.0):
        for index in list(self.lives):
            color, life = self.lives[index]
            add(frame, index, scaled(color, life * strength))
            life -= dt * self.fade
            if life <= 0:
                del self.lives[index]
            else:
                self.lives[index] = (color, life)


class Comets:
    """Bright heads with fading tails that cross the strip."""

    def __init__(self, quantum=3):
        self.quantum = quantum  # heads hop this many pixels at a time, for a choppy look
        self.items = []  # [position, direction, speed, color, tail]

    def launch(self, direction, speed, color, tail, count):
        start = 0.0 if direction > 0 else count - 1.0
        self.items.append([start, direction, speed, color, tail])

    def draw(self, frame, dt, strength=1.0):
        for comet in list(self.items):
            comet[0] += comet[1] * comet[2] * dt
            if not -comet[4] <= comet[0] <= frame.count + comet[4]:
                self.items.remove(comet)
                continue
            for step in range(comet[4]):
                level = (1.0 - step / comet[4]) ** 2
                head = int(comet[0] // self.quantum * self.quantum)
                add(frame, head - comet[1] * step,
                    scaled(comet[3], level * strength))
