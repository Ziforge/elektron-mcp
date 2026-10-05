"""
Perceptual descriptors for captured audio.

These exist so a patch can be judged by something other than assertion. The
set is deliberately small and each one answers a question that comes up when
designing a percussive or tonal sound: how bright is it, how long does it
ring, how noisy versus pitched is it, how many strikes are in it, and how much
energy sits where it should not.

numpy only -- no librosa or scipy, to keep the server's import cost low.
"""

import numpy as np

EPS = 1e-12

# Below SILENT_PEAK there is nothing to describe at all. Between that and
# LOW_LEVEL_PEAK there is only noise floor, and the descriptors computed from
# it look like a bright, noisy percussion hit -- a near-silent capture
# measures as near-perfect sleigh bells. Anything this quiet is flagged so a
# scoring loop cannot mistake silence for success.
SILENT_PEAK = 1e-5
LOW_LEVEL_PEAK = 2e-3


def _mono(audio: np.ndarray) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float64)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    return audio


def _frames(x: np.ndarray, size: int, hop: int) -> np.ndarray:
    if len(x) < size:
        x = np.pad(x, (0, size - len(x)))
    n = 1 + (len(x) - size) // hop
    idx = np.arange(size)[None, :] + hop * np.arange(n)[:, None]
    return x[idx]


def _spectrum(x: np.ndarray, sr: int, size: int = 2048):
    """Average magnitude spectrum across the signal."""
    hop = size // 2
    win = np.hanning(size)
    mag = np.abs(np.fft.rfft(_frames(x, size, hop) * win, axis=1))
    freqs = np.fft.rfftfreq(size, 1 / sr)
    return freqs, mag.mean(axis=0)


def _envelope(x: np.ndarray, sr: int, window_ms: float = 2.0) -> np.ndarray:
    w = max(1, int(sr * window_ms / 1000))
    return np.convolve(np.abs(x), np.ones(w) / w, mode="same")


def resample(audio: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    """Band-limited resample via the frequency domain.

    Reference recordings are usually 44.1 kHz while the Digitone captures at
    48 kHz, so scoring a patch against one needs a rate match. Done in the
    frequency domain rather than by interpolation, because linear
    interpolation adds its own high-frequency error and the comparison here
    is spectral.
    """
    if sr_from == sr_to:
        return np.asarray(audio, dtype=np.float64)

    x = np.asarray(audio, dtype=np.float64)
    n_in = x.shape[0]
    if n_in == 0:
        return x
    n_out = int(round(n_in * sr_to / sr_from))

    def one(col: np.ndarray) -> np.ndarray:
        spec = np.fft.rfft(col)
        out_bins = n_out // 2 + 1
        resized = np.zeros(out_bins, dtype=complex)
        keep = min(spec.size, out_bins)
        resized[:keep] = spec[:keep]
        return np.fft.irfft(resized, n=n_out) * (n_out / n_in)

    if x.ndim == 1:
        return one(x)
    return np.stack([one(x[:, c]) for c in range(x.shape[1])], axis=1)


def decay_time_ms(x: np.ndarray, sr: int, drop_db: float = 20.0) -> float | None:
    """Time from the envelope peak until it falls by drop_db.

    Returns None when the signal never drops that far, which is itself
    informative: the sound is sustaining rather than decaying.
    """
    env = _envelope(x, sr)
    if env.max() <= EPS:
        return None
    peak_i = int(np.argmax(env))
    target = env[peak_i] * (10 ** (-drop_db / 20))
    below = np.flatnonzero(env[peak_i:] < target)
    if below.size == 0:
        return None
    return float(below[0] / sr * 1000)


def onset_count(x: np.ndarray, sr: int, min_gap_ms: float = 12.0) -> int:
    """Count attacks via rectified envelope difference.

    A shaker or sleigh bell shake contains many strikes; a single synth hit
    contains one. That distinction is most of what separates the two.

    The threshold is adaptive (mean plus three standard deviations of the
    rise function) and candidates must sit in the loud part of the sound.
    A fixed fraction-of-peak threshold counted tremolo ripple in a sustained
    tone as dozens of separate attacks.
    """
    env = _envelope(x, sr, window_ms=1.0)
    if env.max() <= EPS:
        return 0

    rise = np.diff(env, prepend=env[0])
    rise[rise < 0] = 0
    if rise.max() <= EPS:
        return 0

    # Smooth the rise function so one attack is one bump, not a cluster.
    w = max(1, int(sr * 0.002))
    rise = np.convolve(rise, np.ones(w) / w, mode="same")

    thresh = max(0.15 * rise.max(), rise.mean() + 3 * rise.std())
    loud_enough = env > 0.1 * env.max()

    gap = int(sr * min_gap_ms / 1000)
    count, last = 0, -gap
    for i in np.flatnonzero((rise > thresh) & loud_enough):
        if i - last >= gap:
            count += 1
            last = int(i)
    return count


def spectral_flatness(mag: np.ndarray) -> float:
    """Geometric over arithmetic mean of the spectrum.

    Near 1 means noise-like, near 0 means tonal. This is the honest way to
    ask 'is this a rattle or a pitched ping' without guessing a fundamental.
    """
    m = mag + EPS
    return float(np.exp(np.mean(np.log(m))) / np.mean(m))


def describe(audio: np.ndarray, sr: int) -> dict:
    """Full descriptor set for one captured sound."""
    x = _mono(audio)
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    rms = float(np.sqrt(np.mean(x**2))) if x.size else 0.0

    result = {
        "samples": int(x.size),
        "duration_ms": round(x.size / sr * 1000, 1),
        "peak": round(peak, 6),
        "rms": round(rms, 6),
        "peak_dbfs": round(20 * np.log10(peak + EPS), 2),
        "crest_factor_db": round(20 * np.log10((peak + EPS) / (rms + EPS)), 2),
    }

    if peak < SILENT_PEAK:
        result["silent"] = True
        result["note"] = (
            "no signal captured; check the device is sounding and that USB "
            "audio is routed on the Digitone"
        )
        return result

    freqs, mag = _spectrum(x, sr)
    total = mag.sum() + EPS

    centroid = float((freqs * mag).sum() / total)
    spread = float(np.sqrt(((freqs - centroid) ** 2 * mag).sum() / total))
    cumulative = np.cumsum(mag) / total
    rolloff95 = float(freqs[np.searchsorted(cumulative, 0.95)])

    def band(lo: float, hi: float) -> float:
        sel = (freqs >= lo) & (freqs < hi)
        return round(float(mag[sel].sum() / total), 4)

    result.update(
        {
            "spectral_centroid_hz": round(centroid, 1),
            "spectral_spread_hz": round(spread, 1),
            "rolloff_95_hz": round(rolloff95, 1),
            "spectral_flatness": round(spectral_flatness(mag), 4),
            "zero_crossing_rate": round(
                float(np.mean(np.abs(np.diff(np.sign(x))) > 0)), 4
            ),
            "bands": {
                "sub_100": band(0, 100),
                "low_100_500": band(100, 500),
                "mid_500_2k": band(500, 2000),
                "high_2k_6k": band(2000, 6000),
                "top_6k_plus": band(6000, sr / 2),
            },
            "energy_below_1k": band(0, 1000),
            "energy_above_2k": band(2000, sr / 2),
            "decay_t20_ms": decay_time_ms(x, sr),
            "onsets": onset_count(x, sr),
        }
    )

    if peak < LOW_LEVEL_PEAK:
        result["low_level"] = True
        result["note"] = (
            f"peak is only {peak:.2e}; these descriptors are measuring noise "
            "floor, not the sound, and must not be treated as a result"
        )
    return result


def mstft_distance(a: np.ndarray, b: np.ndarray, sr: int) -> dict:
    """Multi-resolution log-magnitude STFT distance between two sounds.

    Used to score a patch against a reference recording. Lower is closer.
    Multi-resolution because a single window length favours either the
    transient or the tail, never both.
    """
    xa, xb = _mono(a), _mono(b)
    n = min(len(xa), len(xb))
    if n == 0:
        return {"error": "one of the signals is empty"}
    xa, xb = xa[:n], xb[:n]

    # Match loudness first, so the score reflects timbre rather than level.
    ra = np.sqrt(np.mean(xa**2)) + EPS
    rb = np.sqrt(np.mean(xb**2)) + EPS
    xa, xb = xa / ra, xb / rb

    per_scale = {}
    totals = []
    for size in (256, 1024, 4096):
        hop = size // 4
        win = np.hanning(size)
        fa = np.log(np.abs(np.fft.rfft(_frames(xa, size, hop) * win, axis=1)) + EPS)
        fb = np.log(np.abs(np.fft.rfft(_frames(xb, size, hop) * win, axis=1)) + EPS)
        m = min(len(fa), len(fb))
        d = float(np.mean(np.abs(fa[:m] - fb[:m])))
        per_scale[f"win_{size}"] = round(d, 4)
        totals.append(d)

    return {
        "distance": round(float(np.mean(totals)), 4),
        "per_scale": per_scale,
        "compared_samples": int(n),
    }
