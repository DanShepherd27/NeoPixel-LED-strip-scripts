"""The KITT look on one strip: the nose scanner and the dashboard voice box together.

On the car they are separate pieces of hardware. The scanner on the nose is eight
lamps that sweep at a steady pace and ignore sound: the lit lamp leads and the lamps
behind it fade like cooling bulbs. The voice box on the dashboard is what reacts when
KITT talks: three columns of red segments open from their middles outward with the
voice, and the middle column is the tallest.

This strip shows both. The scanner sweeps a short window in the middle (about as wide
against the strip as the light bar is against the car), so it reads as the scanner,
not as a strip-length chase. The voice box is three segmented bars: the middle one
glows under the scanner window and the two shorter ones sit outside it. Silence
leaves only the scanner; sound opens the bars from their centres.
"""

import math

from arcade.music_dynamics import Dynamics

RED = (255, 0, 0)
SCANNER_SHARE = 0.4               # the window is 24 of 60 LEDs
VOICE_GAP = 2                     # dark LEDs between the window and each outer bar
SEGMENT_ON, SEGMENT_OFF = 2, 1    # lit segments and the dark rules between them


class Layout:
    """Where the scanner window and the three voice bars sit on a strip of ``count``."""

    def __init__(self, count):
        window = min(count, max(4, int(round(count * SCANNER_SHARE))))
        if (count - window) % 2:
            window += 1 if window < count else -1
        self.count = count
        self.window = window
        self.window_start = (count - window) // 2
        middle = (count - 1) / 2.0
        outer = self.window_start - VOICE_GAP
        # (centre, longest half-length, is_middle) for each voice bar
        self.bars = [(middle, window / 2.0, True)]
        if outer >= 3:
            self.bars.append(((outer - 1) / 2.0, outer / 2.0, False))
            self.bars.append((count - 1 - (outer - 1) / 2.0, outer / 2.0, False))


class Scanner:
    """A lamp bar swept at a steady pace; each lamp fades after the head passes.

    The fade is kept per lamp (bulb afterglow), so the tail trails the head and lingers
    for a moment while the head turns at an end, as on the car.
    """

    SWEEP_SECONDS = 0.75   # one pass across the window
    DWELL_SECONDS = 0.06   # the head waits at each end before turning
    AFTERGLOW = 0.085      # seconds for a lamp to fall to 1/e: a tail of about 7 LEDs

    def __init__(self, width):
        self.width = width
        self.clock = 0.0
        self.glow = [0.0] * width
        self._head = 0.0

    def position(self):
        """Head position in the window, 0 to width - 1."""
        leg = self.SWEEP_SECONDS + self.DWELL_SECONDS
        t = self.clock % (2.0 * leg)
        forward = t < leg
        travel = max(0.0, (t if forward else t - leg) - self.DWELL_SECONDS) / self.SWEEP_SECONDS
        share = min(1.0, travel)
        return (share if forward else 1.0 - share) * (self.width - 1)

    def update(self, dt):
        dt = max(0.0, dt)
        self.clock += dt
        fade = math.exp(-dt / self.AFTERGLOW)
        self.glow = [value * fade for value in self.glow]
        previous, head = self._head, self.position()
        self._head = head
        # Light every lamp the head crossed this frame, aged by how long ago it passed,
        # so a slow frame never leaves a gap in the tail.
        speed = (self.width - 1) / self.SWEEP_SECONDS
        low, high = sorted((previous, head))
        for lamp in range(int(math.ceil(low)), int(math.floor(high)) + 1):
            value = math.exp(-abs(head - lamp) / speed / self.AFTERGLOW)
            self.glow[lamp] = max(self.glow[lamp], value)
        self.glow[int(round(head))] = 1.0    # the leading lamp is always fully lit
        return self.glow


class VoiceBox:
    """How far the three voice columns are open, 0-1, from the vocal loudness.

    Loudness is measured against the song's recent loudest moment, so the columns open
    fully on loud passages at any volume. The middle column opens first; the outer
    ones join once the voice passes ``OUTER_START``.
    """

    RISE_PER_SECOND = 10.0   # fastest opening: keeps the bars from flashing the strip
    OUTER_START = 0.2

    def __init__(self):
        self.dynamics = Dynamics()
        self.opening = 0.0

    def update(self, voice, dt, intensity=1.0):
        """``intensity`` (the FX knob, 0-2): higher keeps soft sounds closed and makes
        loud ones open wider and snap harder."""
        energy = self.dynamics.update(voice, dt).energy
        floor = 0.25 * max(0.0, min(2.0, intensity))
        target = max(0.0, energy - floor) / (1.0 - floor)
        if target > self.opening:
            self.opening = min(target, self.opening + self.RISE_PER_SECOND * max(0.0, dt))
        else:
            self.opening = target
        return self.opening

    def outer_opening(self):
        return max(0.0, self.opening - self.OUTER_START) / (1.0 - self.OUTER_START)


def voice_level(level, bands):
    """Loudness of the vocal range (300 Hz-4 kHz) with a little of the whole mix."""
    mids = sum(bands[2:5]) / 3.0 if bands and len(bands) >= 5 else level
    return 0.7 * mids + 0.3 * level


class KittScanner:
    """The live pattern: a steady scanner in the middle, a voice box that follows sound."""

    MIDDLE_BAR_BRIGHTNESS = 0.35   # under the scanner, so the sweeping head stays readable
    OUTER_BAR_BRIGHTNESS = 0.85    # the scanner head (1.0) stays the brightest point

    def __init__(self):
        self.layout = None
        self.scanner = None
        self.voice = VoiceBox()

    def render(self, frame, level, bands, dt, intensity=1.0):
        if self.layout is None or self.layout.count != frame.count:
            self.layout = Layout(frame.count)
            self.scanner = Scanner(self.layout.window)
        layout = self.layout
        brightness = [0.0] * frame.count
        self.voice.update(voice_level(level, bands), dt, intensity)
        for centre, longest, is_middle in layout.bars:
            opening = self.voice.opening if is_middle else self.voice.outer_opening()
            peak = self.MIDDLE_BAR_BRIGHTNESS if is_middle else self.OUTER_BAR_BRIGHTNESS
            _draw_bar(brightness, centre, longest * opening, peak)
        for lamp, glow in enumerate(self.scanner.update(dt)):
            index = layout.window_start + lamp
            brightness[index] = max(brightness[index], glow)
        frame.pixels = [_red(value) for value in brightness]


def _draw_bar(brightness, centre, half_length, peak):
    """A segmented bar opening from ``centre``; its growing tip is anti-aliased."""
    if half_length <= 0.0:
        return
    for index in range(int(centre - half_length) - 1, int(centre + half_length) + 2):
        if not 0 <= index < len(brightness):
            continue
        distance = abs(index - centre)
        if int(distance) % (SEGMENT_ON + SEGMENT_OFF) >= SEGMENT_ON:
            continue
        amount = max(0.0, min(1.0, half_length + 0.5 - distance))
        brightness[index] = max(brightness[index], amount * peak)


def _red(value):
    return tuple(int(channel * max(0.0, min(1.0, value))) for channel in RED)
