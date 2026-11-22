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
    return bands, level, kick, snare


def normalize(series, percentile=98.0, curve=0.6):
    scale = np.percentile(series, percentile) or 1.0
    return np.clip(series / scale, 0.0, 1.0) ** curve


def main():
    source = Path(sys.argv[1])
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "song.wav"
        decode(source, wav_path)
        bands, level, kick, snare = analyze(wav_path)
    data = [normalize(bands[:, b]) for b in range(6)]
    data += [normalize(level), normalize(kick, 97.0, 0.8), normalize(snare, 97.0, 0.8)]
    payload = {
        "frame_rate": FRAME_RATE,
        "frames": int(len(level)),
        "duration": round(len(level) / FRAME_RATE, 3),
        "channels": {
            name: base64.b64encode(bytes((values * 255).astype(np.uint8))).decode("ascii")
            for name, values in zip(CHANNELS, data)
        },
    }
    out = source.with_suffix(".analysis.json")
    out.write_text(json.dumps(payload, separators=(",", ":")))
    print("Wrote", out, "-", payload["frames"], "frames,", payload["duration"], "s")


if __name__ == "__main__":
    main()
