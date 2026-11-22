"""Audio analysis for song shows: loudness, bands, tempo and beat strengths.

Runs offline or on the Pi in a background process (never in the web/LED
process): numpy is imported lazily so the rest of the app does not need it.
Output is the compact ``*.analysis.json`` the cue engine reads.
"""

import base64
import shutil
import struct
import subprocess
import wave
from pathlib import Path

FRAME_RATE = 40
WINDOW = 2048
BAND_EDGES = (20, 120, 300, 800, 2000, 5000, 10000)
CHANNELS = ("sub", "bass", "low_mid", "mid", "high_mid", "high", "level", "kick", "snare")
ONSET_RATE = 100
TEMPO_RANGE = (80.0, 200.0)
TEMPO_PRIOR_CENTER = 130.0   # nudges octave ambiguity toward common dance tempos
ANALYSIS_RATE = 22050
KICK_BAND = (30.0, 150.0)


class AnalysisError(RuntimeError):
    pass


def mp3_info(path):
    """``(sample_rate, samples_per_frame)`` from the first MPEG audio frame header."""
    with open(path, "rb") as audio_file:
        data = audio_file.read(200_000)
    pos = 0
    if data[:3] == b"ID3":  # skip the ID3v2 tag
        size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) | ((data[8] & 0x7F) << 7) | (data[9] & 0x7F)
        pos = 10 + size
    rates = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}
    while pos + 4 <= len(data):
        header = struct.unpack(">I", data[pos:pos + 4])[0]
        version, layer, rate_index = (header >> 19) & 3, (header >> 17) & 3, (header >> 10) & 3
        if (header >> 21) == 0x7FF and version != 1 and layer == 1 and rate_index != 3:
            return rates[version][rate_index], (1152 if version == 3 else 576)
        pos += 1
    raise AnalysisError("no MP3 audio found in the file")


def decode(path, wav_path):
    """Decode to mono 22.05 kHz WAV with whichever decoder the machine has."""
    path = str(path)
    if path.lower().endswith(".wav"):
        shutil.copy(path, wav_path)
        return
    path_str = str(wav_path)
    candidates = [
        ("mpg123", ["mpg123", "-q", "--mono", "-r", str(ANALYSIS_RATE), "-w", path_str, path]),
        ("ffmpeg", ["ffmpeg", "-y", "-loglevel", "error", "-i", path,
                    "-ac", "1", "-ar", str(ANALYSIS_RATE), path_str]),
        ("afconvert", ["afconvert", "-f", "WAVE", "-d", "LEI16@%d" % ANALYSIS_RATE, "-c", "1", path, path_str]),
    ]
    problems = []
    for name, command in candidates:
        if not shutil.which(name):
            continue
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0 and Path(wav_path).exists() and Path(wav_path).stat().st_size > 44:
            return
        problems.append("%s: %s" % (name, result.stderr.strip() or "failed"))
    if not problems:
        raise AnalysisError("no audio decoder found (install mpg123: sudo apt install mpg123)")
    raise AnalysisError("could not decode the audio (%s)" % "; ".join(problems))


def read_wav(wav_path):
    import numpy as np
    with wave.open(str(wav_path)) as wav:
        rate, channels = wav.getframerate(), wav.getnchannels()
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples.astype(np.float32) / 32768.0, rate


def band_features(audio, rate, progress=None):
    """Six frequency bands, loudness, kick and snare onsets at FRAME_RATE."""
    import numpy as np
    hop = rate // FRAME_RATE
    frames = len(audio) // hop
    window = np.hanning(WINDOW)
    freqs = np.fft.rfftfreq(WINDOW, 1.0 / rate)
    masks = [(freqs >= lo) & (freqs < hi) for lo, hi in zip(BAND_EDGES, BAND_EDGES[1:])]
    kick_mask, snare_mask = (freqs >= 30) & (freqs < 200), (freqs >= 1500) & (freqs < 7000)
    padded = np.pad(audio, (WINDOW // 2, WINDOW))
    bands, level = np.zeros((frames, 6)), np.zeros(frames)
    kick, snare = np.zeros(frames), np.zeros(frames)
    previous = None
    for i in range(frames):
        segment = padded[i * hop:i * hop + WINDOW]
        spectrum = np.abs(np.fft.rfft(segment * window))
        for b, mask in enumerate(masks):
            bands[i, b] = spectrum[mask].mean()
        level[i] = np.sqrt((segment ** 2).mean())
        if previous is not None:
            rise = np.maximum(spectrum - previous, 0.0)
            kick[i], snare[i] = rise[kick_mask].sum(), rise[snare_mask].sum()
        previous = spectrum
        if progress and i % 500 == 0:
            progress(i / frames)
    return bands, level, kick, snare


def onset_strength(audio, rate, band=None):
    """Spectral-flux onset curve at ONSET_RATE frames/s (and frame centres); broadband,
    or limited to ``band`` = (low_hz, high_hz)."""
    import numpy as np
    size, hop = 1024, rate // ONSET_RATE
    window = np.hanning(size)
    freqs = np.fft.rfftfreq(size, 1.0 / rate)
    keep = slice(None) if band is None else (freqs >= band[0]) & (freqs < band[1])
    frames = (len(audio) - size) // hop
    index = np.arange(size)[None, :] + hop * np.arange(frames)[:, None]
    chunks = []
    for start in range(0, frames, 2000):  # block-wise FFT keeps memory modest
        block = audio[index[start:start + 2000]] * window
        chunks.append(np.log1p(100 * np.abs(np.fft.rfft(block, axis=1))[:, keep]))
    log_spectra = np.concatenate(chunks)
    flux = np.append(np.maximum(np.diff(log_spectra, axis=0), 0).sum(axis=1), 0.0)
    return flux / (flux.std() or 1.0), (np.arange(frames) * hop + size / 2) / rate


def estimate_bpm(onset):
    """Dominant tempo from the onset curve's autocorrelation, octave-resolved."""
    import numpy as np
    centered = onset - onset.mean()
    spectrum = np.fft.rfft(centered, 2 * len(centered))
    ac = np.fft.irfft(np.abs(spectrum) ** 2)[:len(centered)]
    best_score, best_bpm = -1.0, 120.0
    for lag in range(int(ONSET_RATE * 60 / TEMPO_RANGE[1]), int(ONSET_RATE * 60 / TEMPO_RANGE[0]) + 1):
        bpm = ONSET_RATE * 60.0 / lag
        harmonics = ac[lag] + 0.5 * ac[min(2 * lag, len(ac) - 1)] + 0.25 * ac[min(4 * lag, len(ac) - 1)]
        prior = np.exp(-0.5 * (np.log2(bpm / TEMPO_PRIOR_CENTER) / 0.6) ** 2)
        if harmonics * prior > best_score:
            best_score, best_bpm = harmonics * prior, bpm
    return best_bpm


def track_beats(onset, centres, bpm):
    """Beat grid ``(offset, period)`` for a constant-tempo track.

    Dance and pop tracks are programmed at one tempo, so rather than following
    beats one by one (which wanders through breakdowns where nothing sounds) fold
    the whole onset curve over candidate periods near ``bpm``: the true period is
    the one where onsets pile up at the same phase across the entire track.
    """
    import numpy as np
    bins = 128
    estimate = 60.0 / bpm
    best_score, best_period, best_folded = -1.0, estimate, None
    for scale in np.arange(-0.018, 0.01801, 0.00005):
        period = estimate * (1.0 + scale)
        index = ((centres % period) / period * bins).astype(int)
        folded = np.bincount(index, weights=onset, minlength=bins)[:bins]
        smooth = folded + np.roll(folded, 1) + np.roll(folded, -1)
        if smooth.max() > best_score:
            best_score, best_period, best_folded = smooth.max(), period, smooth
    peak = int(np.argmax(best_folded))
    left, right = best_folded[peak - 1], best_folded[(peak + 1) % bins]
    curve = left - 2 * best_folded[peak] + right
    fraction = 0.5 * (left - right) / curve if curve < 0 else 0.0   # parabolic peak refinement
    offset = (peak + 0.5 + fraction) / bins * best_period
    return offset + 0.5 / ONSET_RATE, best_period   # flux between frames i and i+1 marks time i + half a frame


def kick_phase(bass_onset, centres, offset, period, bins=20):
    """Where, as a distance from the grid in 0..0.5 beats, the kick band's onsets
    concentrate (0 = on the beat, 0.5 = on the off-beat)."""
    import numpy as np
    phase = ((centres - offset) % period) / period
    folded, _ = np.histogram(phase, bins=bins, range=(0, 1), weights=bass_onset)
    peak = (int(np.argmax(folded)) + 0.5) / bins
    return min(peak, 1.0 - peak)


def beat_strengths(onset, centres, offset, period, count, spread=1):
    """Onset strength on every beat and on the off-beat 8th after it (0-1)."""
    import numpy as np

    def sample(times):
        index = np.clip(((times - centres[0]) * ONSET_RATE).astype(int), 0, len(onset) - 1)
        return np.max([onset[np.clip(index + k, 0, len(onset) - 1)] for k in range(-spread, spread + 1)], axis=0)
    beats = offset + np.arange(count) * period
    on, off = sample(beats), sample(beats + period / 2)
    scale = np.percentile(on, 95) or 1.0
    return np.clip(on / scale, 0, 1), np.clip(off / scale, 0, 1)


def _normalize(series, percentile=98.0, curve=0.6):
    import numpy as np
    scale = np.percentile(series, percentile) or 1.0
    return np.clip(series / scale, 0.0, 1.0) ** curve


def _b64(values):
    import numpy as np
    return base64.b64encode(bytes((np.asarray(values) * 255).astype(np.uint8))).decode("ascii")


def analyze_file(audio_path, tmp_dir, progress=None):
    """Analyze an audio file; returns the dictionary written as ``*.analysis.json``."""
    import numpy as np
    step = progress or (lambda fraction, stage: None)
    wav_path = Path(tmp_dir) / "analysis.wav"
    step(0.02, "Decoding audio")
    decode(audio_path, wav_path)
    audio, rate = read_wav(wav_path)
    if len(audio) < rate * 20:
        raise AnalysisError("the track is shorter than 20 seconds")
    step(0.10, "Measuring loudness and frequency bands")
    bands, level, kick, snare = band_features(audio, rate, lambda f: step(0.10 + 0.45 * f, "Measuring loudness and frequency bands"))
    step(0.58, "Finding the tempo")
    onset, centres = onset_strength(audio, rate)
    bpm = estimate_bpm(onset)
    step(0.70, "Tracking the beat")
    offset, period = track_beats(onset, centres, bpm)
    count = int((len(audio) / rate - offset) / period)
    # Off-beat hats can out-shout the kick in the broadband curve. Fold the kick band's
    # onsets over one beat: if they pile up around the half-beat, shift the grid.
    bass, bass_centres = onset_strength(audio, rate, KICK_BAND)
    if kick_phase(bass, bass_centres, offset, period) > 0.25:
        offset += period / 2
        count = int((len(audio) / rate - offset) / period)
    on_beat, off_beat = beat_strengths(onset, centres, offset, period, count)
    step(0.95, "Saving the analysis")
    data = [_normalize(bands[:, b]) for b in range(6)]
    data += [_normalize(level), _normalize(kick, 97.0, 0.8), _normalize(snare, 97.0, 0.8)]
    return {
        "frame_rate": FRAME_RATE,
        "frames": int(len(level)),
        "duration": round(len(level) / FRAME_RATE, 3),
        "tempo": {"bpm": round(60.0 / period, 4), "offset": round(offset, 4)},
        "beat_strength": _b64(on_beat),
        "offbeat_strength": _b64(off_beat),
        "channels": {name: _b64(values) for name, values in zip(CHANNELS, data)},
    }
