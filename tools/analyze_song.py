"""Offline analysis that feeds the song choreography (development tool).

Decodes an MP3 to mono 22.05 kHz audio, then writes a compact JSON file with
per-frame (40 Hz) loudness, six frequency bands (the same ranges the live
visualizer uses) and bass/snare onset strengths. The Pi never runs this; it
just loads the resulting JSON. Requires numpy plus ffmpeg or macOS afconvert:

    python tools/analyze_song.py assets/song/all-i-want-for-christmas-is-you.mp3
"""

import base64
import json
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

FRAME_RATE = 40
WINDOW = 2048
BAND_EDGES = (20, 120, 300, 800, 2000, 5000, 10000)
CHANNELS = ("sub", "bass", "low_mid", "mid", "high_mid", "high", "level", "kick", "snare")


def decode(path, wav_path):
    if shutil.which("ffmpeg"):
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path),
               "-ac", "1", "-ar", "22050", str(wav_path)]
    elif shutil.which("afconvert"):
        cmd = ["afconvert", "-f", "WAVE", "-d", "LEI16@22050", "-c", "1",
               str(path), str(wav_path)]
    else:
        raise SystemExit("Install ffmpeg (or use macOS afconvert) to decode the MP3.")
    subprocess.run(cmd, check=True)


def analyze(wav_path):
    with wave.open(str(wav_path)) as wav:
        rate = wav.getframerate()
        audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
    audio = audio.astype(np.float32) / 32768.0
    hop = rate // FRAME_RATE
    frames = len(audio) // hop
    window = np.hanning(WINDOW)
    freqs = np.fft.rfftfreq(WINDOW, 1.0 / rate)
    masks = [(freqs >= lo) & (freqs < hi) for lo, hi in zip(BAND_EDGES, BAND_EDGES[1:])]
    padded = np.pad(audio, (WINDOW // 2, WINDOW))  # centre each window on its frame
    bands = np.zeros((frames, 6))
    level = np.zeros(frames)
    kick = np.zeros(frames)
    snare = np.zeros(frames)
    previous = None
    for i in range(frames):
        segment = padded[i * hop:i * hop + WINDOW]
        spectrum = np.abs(np.fft.rfft(segment * window))
        for b, mask in enumerate(masks):
            bands[i, b] = spectrum[mask].mean()
        level[i] = np.sqrt((segment ** 2).mean())
        if previous is not None:
            rise = np.maximum(spectrum - previous, 0.0)
            kick[i] = rise[(freqs >= 30) & (freqs < 200)].sum()
            snare[i] = rise[(freqs >= 1500) & (freqs < 7000)].sum()
        previous = spectrum
    return audio, rate, bands, level, kick, snare


ONSET_RATE = 100
EXPECTED_BPM = 150.0


def onset_strength(audio, rate):
    """Broadband spectral-flux onset curve at ONSET_RATE frames/s (centres in seconds)."""
    size, hop = 1024, rate // ONSET_RATE
    window = np.hanning(size)
    frames = (len(audio) - size) // hop
    log_spectra = np.log1p(100 * np.abs(np.array([
        np.fft.rfft(audio[i * hop:i * hop + size] * window) for i in range(frames)
    ])))
    flux = np.maximum(np.diff(log_spectra, axis=0), 0).sum(axis=1)
    flux = np.append(flux, 0.0)
    return flux / flux.std(), (np.arange(frames) * hop + size / 2) / rate


def track_beats(onset, centres):
    """Dynamic-programming beat tracker (Ellis 2007) near EXPECTED_BPM, then a
    straight-line fit, because the song is programmed at a constant tempo."""
    period = ONSET_RATE * 60.0 / EXPECTED_BPM
    score = onset.copy()
    back = -np.ones(len(onset), int)
    for i in range(len(onset)):
        taus = np.arange(max(0, int(i - 1.3 * period)), int(i - 0.75 * period))
        if len(taus) == 0:
            continue
        candidate = score[taus] - 400.0 * np.log((i - taus) / period) ** 2
        best = candidate.argmax()
        score[i] = onset[i] + candidate[best]
        back[i] = taus[best]
    i = int(np.argmax(score[-300:])) + len(onset) - 300
    beats = []
    while i >= 0:
        beats.append(i)
        i = back[i]
    times = centres[np.array(beats[::-1])]
    index = np.arange(len(times))
    design = np.vstack([np.ones_like(index), index]).T
    coef = np.linalg.lstsq(design, times, rcond=None)[0]
    for _ in range(3):  # drop beats the tracker mis-snapped, then refit
        keep = np.abs(times - design @ coef) < 0.02
        coef = np.linalg.lstsq(design[keep], times[keep], rcond=None)[0]
    return coef[0], coef[1]


def beat_strengths(onset, centres, offset, period, count):
    """Onset strength on every beat and on the off-beat 8th after it (0-1)."""
    def sample(times):
        index = np.clip(((times - centres[0]) * ONSET_RATE).astype(int), 0, len(onset) - 1)
        return np.max([onset[np.clip(index + k, 0, len(onset) - 1)] for k in (-1, 0, 1)], axis=0)
    beats = offset + np.arange(count) * period
    on, off = sample(beats), sample(beats + period / 2)
    scale = np.percentile(on, 95) or 1.0
    return np.clip(on / scale, 0, 1), np.clip(off / scale, 0, 1)


def b64(values):
    return base64.b64encode(bytes((np.asarray(values) * 255).astype(np.uint8))).decode("ascii")


def normalize(series, percentile=98.0, curve=0.6):
    scale = np.percentile(series, percentile) or 1.0
    return np.clip(series / scale, 0.0, 1.0) ** curve


def main():
    source = Path(sys.argv[1])
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "song.wav"
        decode(source, wav_path)
        audio, rate, bands, level, kick, snare = analyze(wav_path)
    onset, centres = onset_strength(audio, rate)
    offset, period = track_beats(onset, centres)
    offset += 0.5 / ONSET_RATE  # flux between frames i and i+1 marks time i + half a frame
    beat_count = int((len(audio) / rate - offset) / period)
    on_beat, off_beat = beat_strengths(onset, centres, offset, period, beat_count)
    print("Tempo %.3f BPM, first beat at %.3f s" % (60.0 / period, offset))
    data = [normalize(bands[:, b]) for b in range(6)]
    data += [normalize(level), normalize(kick, 97.0, 0.8), normalize(snare, 97.0, 0.8)]
    payload = {
        "frame_rate": FRAME_RATE,
        "frames": int(len(level)),
        "duration": round(len(level) / FRAME_RATE, 3),
        "tempo": {"bpm": round(60.0 / period, 4), "offset": round(float(offset), 4)},
        "beat_strength": b64(on_beat),
        "offbeat_strength": b64(off_beat),
        "channels": {
            name: b64(values)
            for name, values in zip(CHANNELS, data)
        },
    }
    out = source.with_suffix(".analysis.json")
    out.write_text(json.dumps(payload, separators=(",", ":")))
    print("Wrote", out, "-", payload["frames"], "frames,", payload["duration"], "s")


if __name__ == "__main__":
    main()
