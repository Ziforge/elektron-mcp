"""
Audition tools: trigger a sound, capture it, describe what came back.

This is what turns parameter-sending into sound design. Without it a patch
can only be reasoned about; with it a patch can be measured, compared against
a reference recording, and iterated on.
"""

import time

from elektron_mcp.audio import analysis, capture


def _play(midi, track, note, velocity, duration_ms, tail_ms):
    midi.send_note_on(track, note, velocity)
    time.sleep(duration_ms / 1000.0)
    midi.send_note_off(track, note)
    time.sleep(tail_ms / 1000.0)


def _trigger_and_capture(midi, track, note, velocity, duration_ms, tail_ms, device):
    """Record across the whole event, starting before the note.

    The attack is the most informative part of a percussive sound, so
    recording has to begin before the trigger rather than after it.

    Tries an in-process stream first because it is faster, then falls back to
    recording in a child process: a long-lived server can end up unable to
    reopen the device at all, while a fresh process always can.
    """
    settle = 0.08
    try:
        with capture.Recorder(device=device) as rec:
            time.sleep(settle)
            _play(midi, track, note, velocity, duration_ms, tail_ms)
            return rec.audio, rec.samplerate
    except capture.CaptureError:
        total = settle + (duration_ms + tail_ms) / 1000.0 + 0.1
        rec = capture.SubprocessRecorder(total, device=device).start()
        time.sleep(settle)
        _play(midi, track, note, velocity, duration_ms, tail_ms)
        return rec.finish()


def register_audition_tools(mcp, midi):
    """Register capture and analysis tools with the MCP server."""

    @mcp.tool()
    def list_audio_inputs() -> dict:
        """
        List audio input devices visible to the host.

        Use this when a capture comes back silent, to confirm the Digitone is
        present as an input.

        Returns:
            dict: Available input devices with channel counts and sample rates.
        """
        return {"inputs": capture.list_input_devices(),
                "default": capture.DEFAULT_DEVICE}

    @mcp.tool()
    def audition(
        track: int,
        note: int = 84,
        velocity: int = 110,
        duration_ms: int = 300,
        tail_ms: int = 700,
        save_as: str | None = None,
        device: str = capture.DEFAULT_DEVICE,
    ) -> dict:
        """
        Play one note and measure the sound that comes back.

        Recording starts before the note so the attack is captured. Blocks for
        roughly duration_ms + tail_ms.

        Args:
            track (int): Digitone track / MIDI channel, 1-16.
            note (int): MIDI note number. 84 (C6) suits bright percussion.
            velocity (int): Note velocity, 1-127.
            duration_ms (int): How long the note is held.
            tail_ms (int): Extra recording after note off, to catch the decay.
            save_as (str): Optional path to write the capture as 16-bit WAV.
            device (str): Audio input device name.

        Returns:
            dict: Descriptors for the captured sound -- level, spectral
            centroid and spread, band energies, spectral flatness (near 0 is
            tonal, near 1 is noise-like), T20 decay time and onset count.
            'silent' is set when nothing was captured.
        """
        if not 1 <= track <= 16:
            return {"error": f"track must be 1-16, got {track}"}

        try:
            audio, sr = _trigger_and_capture(
                midi, track, note, velocity,
                max(1, duration_ms), max(0, tail_ms), device,
            )
        except capture.CaptureError as e:
            return {"error": str(e), "inputs": capture.list_input_devices()}

        result = analysis.describe(audio, sr)
        result["trigger"] = {"track": track, "note": note, "velocity": velocity}
        if save_as:
            result["saved_to"] = capture.save_wav(audio, sr, save_as)
        return result

    @mcp.tool()
    def audition_sequence(
        track: int,
        notes: list[int],
        step_ms: int = 125,
        velocities: list[int] | None = None,
        gate: float = 0.5,
        repeats: int = 1,
        save_as: str | None = None,
        device: str = capture.DEFAULT_DEVICE,
    ) -> dict:
        """
        Play a pattern and measure the whole phrase.

        Useful where a single hit is not the thing being judged -- a shaker or
        sleigh bell pattern is about onset density and variation across hits,
        which one note cannot show.

        Args:
            track (int): Digitone track / MIDI channel, 1-16.
            notes (list[int]): MIDI note numbers, one per step.
            step_ms (int): Step length in milliseconds.
            velocities (list[int]): Optional per-step velocities, cycled.
            gate (float): Fraction of each step the note is held, 0.05-1.0.
            repeats (int): Times to repeat the pattern, 1-16.
            save_as (str): Optional path to write the capture as 16-bit WAV.
            device (str): Audio input device name.

        Returns:
            dict: Descriptors for the whole phrase plus onsets_per_second.
        """
        if not notes:
            return {"error": "notes list is empty"}
        if not 1 <= track <= 16:
            return {"error": f"track must be 1-16, got {track}"}

        repeats = max(1, min(16, repeats))
        step_ms = max(10, min(2000, step_ms))
        gate = max(0.05, min(1.0, gate))
        steps = list(notes) * repeats

        def _run():
            on_ms = step_ms * gate
            for i, n in enumerate(steps):
                vel = velocities[i % len(velocities)] if velocities else 100
                midi.send_note_on(track, n, vel)
                time.sleep(on_ms / 1000.0)
                midi.send_note_off(track, n)
                time.sleep((step_ms - on_ms) / 1000.0)
            time.sleep(0.4)

        try:
            try:
                with capture.Recorder(device=device) as rec:
                    time.sleep(0.08)
                    _run()
                    audio, sr = rec.audio, rec.samplerate
            except capture.CaptureError:
                total = 0.08 + len(steps) * step_ms / 1000.0 + 0.5
                rec = capture.SubprocessRecorder(total, device=device).start()
                time.sleep(0.08)
                _run()
                audio, sr = rec.finish()
        except capture.CaptureError as e:
            return {"error": str(e), "inputs": capture.list_input_devices()}

        result = analysis.describe(audio, sr)
        seconds = result.get("duration_ms", 0) / 1000.0
        if seconds > 0:
            result["onsets_per_second"] = round(result.get("onsets", 0) / seconds, 2)
        result["pattern"] = {"steps": len(steps), "step_ms": step_ms, "gate": gate}
        if save_as:
            result["saved_to"] = capture.save_wav(audio, sr, save_as)
        return result

    @mcp.tool()
    def capture_and_analyze(
        seconds: float = 2.0,
        save_as: str | None = None,
        device: str = capture.DEFAULT_DEVICE,
    ) -> dict:
        """
        Record the input for a fixed time without triggering anything.

        For listening to something played by hand or by an external sequencer.

        Args:
            seconds (float): How long to record, 0.01-30.
            save_as (str): Optional path to write the capture as 16-bit WAV.
            device (str): Audio input device name.

        Returns:
            dict: Descriptors for the captured audio.
        """
        try:
            try:
                audio, sr = capture.record(seconds, device=device)
            except capture.CaptureError:
                audio, sr = capture.SubprocessRecorder(
                    seconds, device=device
                ).start().finish()
        except capture.CaptureError as e:
            return {"error": str(e), "inputs": capture.list_input_devices()}

        result = analysis.describe(audio, sr)
        if save_as:
            result["saved_to"] = capture.save_wav(audio, sr, save_as)
        return result

    @mcp.tool()
    def analyze_wav_file(path: str) -> dict:
        """
        Describe an existing 16-bit WAV file.

        Use it to characterise a reference recording before trying to match it.

        Args:
            path (str): Path to a 16-bit WAV file.

        Returns:
            dict: Descriptors for the file.
        """
        try:
            audio, sr = capture.load_wav(path)
        except Exception as e:
            return {"error": f"could not read {path}: {e}"}
        result = analysis.describe(audio, sr)
        result["path"] = path
        return result

    @mcp.tool()
    def score_against_reference(
        reference_wav: str,
        track: int,
        note: int = 84,
        velocity: int = 110,
        duration_ms: int = 300,
        tail_ms: int = 700,
        save_as: str | None = None,
        device: str = capture.DEFAULT_DEVICE,
    ) -> dict:
        """
        Audition the current patch and score it against a reference recording.

        The score is a multi-resolution log-magnitude STFT distance with
        loudness matched first, so it reflects timbre rather than level. Lower
        is closer. Use it to drive parameter changes toward a target sound
        instead of judging by description alone.

        Args:
            reference_wav (str): Path to the 16-bit WAV to match.
            track (int): Digitone track / MIDI channel, 1-16.
            note (int): MIDI note number to trigger.
            velocity (int): Note velocity, 1-127.
            duration_ms (int): How long the note is held.
            tail_ms (int): Extra recording after note off.
            save_as (str): Optional path to write the capture as 16-bit WAV.
            device (str): Audio input device name.

        Returns:
            dict: 'score' with the distance, plus descriptors for both the
            capture and the reference so the difference can be read
            parameter-wise rather than as one number.
        """
        try:
            ref, ref_sr = capture.load_wav(reference_wav)
        except Exception as e:
            return {"error": f"could not read {reference_wav}: {e}"}

        try:
            audio, sr = _trigger_and_capture(
                midi, track, note, velocity,
                max(1, duration_ms), max(0, tail_ms), device,
            )
        except capture.CaptureError as e:
            return {"error": str(e), "inputs": capture.list_input_devices()}

        if ref_sr != sr:
            return {
                "error": f"reference is {ref_sr} Hz but capture is {sr} Hz; "
                "resample the reference first"
            }

        result = {
            "score": analysis.mstft_distance(audio, ref, sr),
            "captured": analysis.describe(audio, sr),
            "reference": analysis.describe(ref, ref_sr),
        }
        if save_as:
            result["saved_to"] = capture.save_wav(audio, sr, save_as)
        return result
