"""Speaker-to-microphone latency measurement.

The Pi plays the song while its own microphone listens. Because the song's
loudness over time is known exactly (from the analysis file), sliding that
known envelope against the microphone's envelope finds how long after
starting the player the sound actually leaves the speakers. That delay is
what the lights must be shifted by to land on the beat.
"""

import math
import threading

GRID = 0.025            # seconds between compared samples (40 Hz)
LAG_STEP = 0.005        # candidate latencies are tested every 5 ms
SMOOTHING_SECONDS = 0.5  # envelope trend removed so only changes are compared
MIN_SCORE = 0.30        # correlation needed to trust a result
MIN_MARGIN = 0.06       # how far the best lag must beat the best alternative
ALTERNATIVE_EXCLUSION = 0.12


def _mic_envelope(history, origin, first, count):
    """Mic loudness on the comparison grid, times measured from ``origin``."""
    points = sorted(
        (arrival - duration / 2.0 - origin, math.sqrt(rms))
        for arrival, rms, duration in history
    )
    if not points:
        return None
    values, cursor = [], 0
    for i in range(count):
        t = first + i * GRID
        while cursor + 1 < len(points) and points[cursor + 1][0] <= t:
            cursor += 1
        before = points[cursor]
        after = points[min(cursor + 1, len(points) - 1)]
        if after[0] > before[0] and before[0] <= t <= after[0]:
            mix = (t - before[0]) / (after[0] - before[0])
            values.append(before[1] + (after[1] - before[1]) * mix)
        else:
            values.append(before[1])
    return values


def _detrend(values):
    """Subtract a moving average so slow level changes do not dominate."""
    radius = max(1, int(SMOOTHING_SECONDS / GRID / 2))
    prefix = [0.0]
    for value in values:
        prefix.append(prefix[-1] + value)
    result = []
    for i, value in enumerate(values):
        lo, hi = max(0, i - radius), min(len(values), i + radius + 1)
        result.append(value - (prefix[hi] - prefix[lo]) / (hi - lo))
    return result


def _correlation(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return dot / norm if norm > 1e-12 else 0.0


def estimate_latency(history, origin, analysis, window, lag_range):
    """Find the latency (seconds) that best aligns the song with the microphone.

    ``history`` holds (arrival, rms, seconds) mic chunks; ``origin`` is the
    monotonic time the song clock started; ``window`` is the (start, end)
    seconds after origin to compare; ``lag_range`` the latencies to test.
    """
    steps = int(round(GRID / LAG_STEP))
    first = round(window[0] / LAG_STEP) * LAG_STEP
    count = int((window[1] - first) / GRID)
    mic = _mic_envelope(history, origin, first, count)
    if mic is None or count < 40:
        return {"ok": False, "message": "No microphone audio was captured."}
    mic = _detrend(mic)
    lags = [lag_range[0] + k * LAG_STEP
            for k in range(int(round((lag_range[1] - lag_range[0]) / LAG_STEP)) + 1)]
    reference = analysis.level_series(
        LAG_STEP, int((window[1] - lag_range[0]) / LAG_STEP) + steps + 2,
        first=first - lag_range[1] - LAG_STEP,
    )
    base = int(round((lag_range[1] + LAG_STEP) / LAG_STEP))
    scores = []
    for lag in lags:
        shift = base - int(round(lag / LAG_STEP))
        series = [reference[shift + i * steps] for i in range(count)]
        scores.append(_correlation(mic, _detrend([math.sqrt(v) for v in series])))
    best = max(range(len(scores)), key=scores.__getitem__)
    peak = scores[best]
    offset = 0.0
    if 0 < best < len(scores) - 1:  # parabolic refinement between 5 ms steps
        left, right = scores[best - 1], scores[best + 1]
        denominator = left - 2 * peak + right
        if denominator < 0:
            offset = 0.5 * (left - right) / denominator * LAG_STEP
    rivals = [score for lag, score in zip(lags, scores)
              if abs(lag - lags[best]) >= ALTERNATIVE_EXCLUSION]
    margin = peak - max(rivals) if rivals else peak
    return {
        "ok": peak >= MIN_SCORE and margin >= MIN_MARGIN,
        "latency_ms": round((lags[best] + offset) * 1000.0, 1),
        "score": round(peak, 3),
        "margin": round(margin, 3),
        "curve": [[round(lag * 1000), round(score, 3)]
                  for lag, score in list(zip(lags, scores))[::4]],
    }


class BackgroundMeasurement:
    """Runs estimate_latency off the render thread; poll for the result."""

    def __init__(self, history, origin, analysis, window, lag_range):
        self.result = None
        self._thread = threading.Thread(
            target=self._run, args=(history, origin, analysis, window, lag_range),
            name="latency-measurement", daemon=True,
        )
        self._thread.start()

    def _run(self, *args):
        try:
            self.result = estimate_latency(*args)
        except Exception as exc:  # never let a measurement bug reach the LEDs
            self.result = {"ok": False, "message": "Measurement failed: %s" % exc}
