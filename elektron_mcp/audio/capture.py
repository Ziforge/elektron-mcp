"""
Audio capture from the Digitone's USB output.

The Digitone II presents itself as a 2-channel 48 kHz input device, so the
server can hear what it just programmed. Everything here is synchronous and
short-lived: a capture is a few hundred milliseconds of audio taken while a
note is triggered.
"""

import logging
import wave
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_DEVICE = "Elektron Digitone II"
DEFAULT_SR = 48000
MAX_SECONDS = 30.0


class CaptureError(RuntimeError):
    """Raised when no audio could be captured."""


def list_input_devices() -> list[dict]:
    """Every input device visible to the host, for diagnosing a silent capture."""
    import sounddevice as sd

    return [
        {
            "index": i,
            "name": d["name"],
            "channels": d["max_input_channels"],
            "samplerate": int(d["default_samplerate"]),
        }
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]


def record(
    seconds: float,
    device: str | int = DEFAULT_DEVICE,
    samplerate: int = DEFAULT_SR,
    channels: int = 2,
) -> tuple[np.ndarray, int]:
    """Record a fixed span of audio. Blocks for `seconds`."""
    import sounddevice as sd

    seconds = max(0.01, min(MAX_SECONDS, float(seconds)))
    try:
        buf = sd.rec(
            int(samplerate * seconds),
            samplerate=samplerate,
            channels=channels,
            device=device,
            dtype="float32",
        )
        sd.wait()
    except Exception as e:
        raise CaptureError(f"capture from {device!r} failed: {e}") from e
    return np.asarray(buf), samplerate


class Recorder:
    """Non-blocking capture, so a note can be triggered while recording.

    Used by the audition tools: start the recorder, send the note, stop and
    analyse. Capturing after the trigger would miss the attack, which is the
    part that matters most for percussion.
    """

    def __init__(
        self,
        device: str | int = DEFAULT_DEVICE,
        samplerate: int = DEFAULT_SR,
        channels: int = 2,
    ):
        self.device = device
        self.samplerate = samplerate
        self.channels = channels
        self._blocks: list[np.ndarray] = []
        self._stream = None

    def __enter__(self):
        import sounddevice as sd

        def callback(indata, frames, time_info, status):
            if status:
                logger.debug(f"capture status: {status}")
            self._blocks.append(indata.copy())

        try:
            self._stream = sd.InputStream(
                samplerate=self.samplerate,
                channels=self.channels,
                device=self.device,
                dtype="float32",
                callback=callback,
            )
            self._stream.start()
        except Exception as e:
            raise CaptureError(f"could not open {self.device!r}: {e}") from e
        return self

    def __exit__(self, *exc):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        return False

    @property
    def audio(self) -> np.ndarray:
        if not self._blocks:
            return np.zeros((0, self.channels), dtype=np.float32)
        return np.concatenate(self._blocks, axis=0)


def save_wav(audio: np.ndarray, samplerate: int, path: str | Path) -> str:
    """Write a capture to 16-bit WAV so it can be kept or compared later."""
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(audio, dtype=np.float32)
    if data.ndim == 1:
        data = data[:, None]
    clipped = np.clip(data, -1.0, 1.0)
    pcm = (clipped * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(data.shape[1])
        w.setsampwidth(2)
        w.setframerate(samplerate)
        w.writeframes(pcm.tobytes())
    return str(path)


def load_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Read a WAV file, for scoring a patch against a reference recording."""
    path = Path(path).expanduser()
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        width = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise CaptureError(f"{path} is {width * 8}-bit; only 16-bit WAV is supported")
    audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        audio = audio.reshape(-1, ch)
    return audio, sr
