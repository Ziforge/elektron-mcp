"""
Note and transport tools.

Without these the server can shape a sound but never trigger one, so a patch
can only be judged by sending notes from a sequencer by hand. `play_sequence`
also carries optional per-step parameter jitter, because percussion patches
(shakers, sleigh bells, rattles) read as synthetic when every hit is identical.
"""

import random
import time

from elektron_mcp.digitone.data.sections import SECTIONS

MAX_STEPS = 256
MAX_DURATION_MS = 10_000


def register_play_tools(mcp, midi):
    """Register note, sequence and panic tools with the MCP server."""

    @mcp.tool()
    def play_note(
        track: int,
        note: int = 60,
        velocity: int = 100,
        duration_ms: int = 500,
    ) -> dict:
        """
        Play a single note on a track and release it after a fixed time.

        Blocks for duration_ms, so keep it short when auditioning.

        Args:
            track (int): Digitone track / MIDI channel, 1-16.
            note (int): MIDI note number, 0-127. 60 is middle C.
            velocity (int): Note velocity, 1-127.
            duration_ms (int): How long to hold the note, 1-10000 ms.

        Returns:
            dict: The note played, or an error description.
        """
        if not 1 <= track <= 16:
            return {"error": f"track must be 1-16, got {track}"}
        if not 0 <= note <= 127:
            return {"error": f"note must be 0-127, got {note}"}

        duration_ms = max(1, min(MAX_DURATION_MS, duration_ms))

        if not midi.send_note_on(track, note, velocity):
            return {"error": "failed to send note on"}
        time.sleep(duration_ms / 1000.0)
        midi.send_note_off(track, note)

        return {"track": track, "note": note, "velocity": velocity,
                "duration_ms": duration_ms}

    @mcp.tool()
    def hold_note(track: int, note: int = 60, velocity: int = 100) -> dict:
        """
        Start a note and leave it sounding. Use release_note or all_notes_off
        to stop it. Does not block, so parameters can be changed while the
        note rings.

        Args:
            track (int): Digitone track / MIDI channel, 1-16.
            note (int): MIDI note number, 0-127.
            velocity (int): Note velocity, 1-127.

        Returns:
            dict: The note held, or an error description.
        """
        if not midi.send_note_on(track, note, velocity):
            return {"error": "failed to send note on"}
        return {"held": {"track": track, "note": note}}

    @mcp.tool()
    def release_note(track: int, note: int = 60) -> dict:
        """
        Release a note started by hold_note.

        Args:
            track (int): Digitone track / MIDI channel, 1-16.
            note (int): MIDI note number, 0-127.

        Returns:
            dict: The note released.
        """
        midi.send_note_off(track, note)
        return {"released": {"track": track, "note": note}}

    @mcp.tool()
    def play_sequence(
        track: int,
        notes: list[int],
        step_ms: int = 125,
        velocities: list[int] | None = None,
        gate: float = 0.5,
        repeats: int = 1,
        section: str | None = None,
        jitter: dict[str, int] | None = None,
    ) -> dict:
        """
        Play a sequence of notes at a fixed step length.

        Args:
            track (int): Digitone track / MIDI channel, 1-16.
            notes (list[int]): MIDI note numbers, one per step.
            step_ms (int): Step length in milliseconds. 125 is a 16th at 120 BPM.
            velocities (list[int]): Optional per-step velocities, cycled if
                shorter than notes. Accents are what make a pattern read as
                played rather than programmed.
            gate (float): Fraction of the step the note is held, 0.05-1.0.
            repeats (int): How many times to play the whole sequence, 1-64.
            section (str): Section name to resolve jitter parameter names
                against, e.g. 'fm_drum'. Required when jitter is used.
            jitter (dict[str, int]): Optional {parameter: spread} applied as a
                fresh random offset before every step, e.g.
                {'gran': 14, 'nlev': 10}. Spread is in raw MIDI units either
                side of the value last sent by this call's own jitter base,
                taken from each parameter's default.

        Returns:
            dict: Steps played and any jitter parameters that could not be
            resolved.
        """
        if not 1 <= track <= 16:
            return {"error": f"track must be 1-16, got {track}"}
        if not notes:
            return {"error": "notes list is empty"}

        repeats = max(1, min(64, repeats))
        steps = list(notes) * repeats
        if len(steps) > MAX_STEPS:
            return {"error": f"sequence is {len(steps)} steps; limit is {MAX_STEPS}"}

        step_ms = max(10, min(2000, step_ms))
        gate = max(0.05, min(1.0, gate))

        jitter_ccs: dict[str, tuple[int, int, int]] = {}
        unknown: list[str] = []
        if jitter:
            if section not in SECTIONS:
                return {"error": f"jitter needs a valid section; got {section!r}"}
            params = SECTIONS[section]
            for name, spread in jitter.items():
                if name not in params:
                    unknown.append(name)
                    continue
                base = params[name].get("default") or 64
                jitter_ccs[name] = (int(params[name]["cc_msb"]),
                                    int(base), int(spread))

        on_ms = step_ms * gate
        played = 0
        for i, note in enumerate(steps):
            if velocities:
                vel = velocities[i % len(velocities)]
            else:
                vel = 100

            for cc, base, spread in jitter_ccs.values():
                value = max(0, min(127, base + random.randint(-spread, spread)))
                midi.send_cc(track, cc, value)

            midi.send_note_on(track, note, vel)
            time.sleep(on_ms / 1000.0)
            midi.send_note_off(track, note)
            time.sleep((step_ms - on_ms) / 1000.0)
            played += 1

        result = {"track": track, "steps_played": played, "step_ms": step_ms,
                  "gate": gate}
        if unknown:
            result["unknown_jitter_params"] = unknown
        return result

    @mcp.tool()
    def all_notes_off(track: int | None = None) -> dict:
        """
        Silence stuck notes on one track, or every track if none is given.

        Args:
            track (int): Digitone track / MIDI channel 1-16, or omit for all.

        Returns:
            dict: Which tracks were silenced.
        """
        ok = midi.all_notes_off(track)
        return {"silenced": track if track else "all tracks", "ok": ok}

    @mcp.tool()
    def set_program(track: int, program: int) -> dict:
        """
        Send a Program Change to select a sound or pattern slot.

        Args:
            track (int): Digitone track / MIDI channel, 1-16.
            program (int): Program number, 0-127.

        Returns:
            dict: The program selected, or an error description.
        """
        if not 0 <= program <= 127:
            return {"error": f"program must be 0-127, got {program}"}
        ok = midi.send_program_change(track, program)
        return {"track": track, "program": program, "ok": ok}
