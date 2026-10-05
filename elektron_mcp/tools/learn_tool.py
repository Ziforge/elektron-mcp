"""
MIDI-learn tools: find out what the Digitone sends.

Parameter maps in this repo were transcribed from documentation. These tools
let the hardware answer for itself -- turn a knob, see which CC or NRPN moved.
That is also the only honest way to test whether machine selection emits
anything at all, which no CC map covers.

Requires 'Send CC/NRPN' enabled in the Digitone's MIDI config (SETTINGS >
MIDI CONFIG > PORT CONFIG). An empty capture usually means that is off.
"""

import time

from elektron_mcp.digitone.data.sections import SECTIONS


def _known_cc() -> dict[int, list[str]]:
    """Reverse index from CC number to the parameters that claim it."""
    index: dict[int, list[str]] = {}
    for section, params in SECTIONS.items():
        for ident, spec in params.items():
            if "cc_msb" not in spec:
                # NRPN-only, so no incoming CC can correspond to it.
                continue
            index.setdefault(int(spec["cc_msb"]), []).append(f"{section}.{ident}")
    return index


def _summarise(events: list) -> dict:
    """Aggregate captured messages into something readable."""
    known = _known_cc()
    ccs: dict[str, dict] = {}
    notes: list[dict] = []
    programs: list[dict] = []
    sysex: list[dict] = []
    nrpn_raw: list[dict] = []

    # NRPN arrives as CC 99/98 (parameter) then CC 6/38 (value).
    pending: dict[int, dict] = {}

    for ts, msg in events:
        kind = msg.type
        if kind == "control_change":
            ch, cc, val = msg.channel + 1, msg.control, msg.value
            if cc in (99, 98, 6, 38):
                slot = pending.setdefault(ch, {})
                slot[{99: "msb", 98: "lsb", 6: "data_msb", 38: "data_lsb"}[cc]] = val
                if "msb" in slot and "lsb" in slot and "data_msb" in slot:
                    nrpn_raw.append({"channel": ch, **slot})
                    pending[ch] = {}
                continue
            key = f"ch{ch}_cc{cc}"
            entry = ccs.setdefault(
                key,
                {
                    "channel": ch,
                    "cc": cc,
                    "count": 0,
                    "min": val,
                    "max": val,
                    "last": val,
                    "maps_to": known.get(cc, []),
                },
            )
            entry["count"] += 1
            entry["min"] = min(entry["min"], val)
            entry["max"] = max(entry["max"], val)
            entry["last"] = val
        elif kind in ("note_on", "note_off"):
            notes.append({"channel": msg.channel + 1, "type": kind,
                          "note": msg.note, "velocity": msg.velocity})
        elif kind == "program_change":
            programs.append({"channel": msg.channel + 1, "program": msg.program})
        elif kind == "sysex":
            data = list(msg.data)
            sysex.append({"length": len(data), "head": data[:12]})

    result = {
        "messages": len(events),
        "control_changes": ccs,
        "nrpn": nrpn_raw,
    }
    if notes:
        result["notes"] = notes[:40]
    if programs:
        result["program_changes"] = programs
    if sysex:
        result["sysex"] = sysex[:10]
    if not events:
        result["note"] = (
            "nothing captured -- check SETTINGS > MIDI CONFIG > PORT CONFIG "
            "has 'Send CC/NRPN' (or OUT CHANNEL) enabled on the Digitone"
        )
    return result


def register_learn_tools(mcp, midi):
    """Register MIDI capture tools with the MCP server."""

    @mcp.tool()
    def start_midi_capture() -> dict:
        """
        Start recording MIDI coming from the Digitone.

        Call this, then move a control on the device, then call
        get_captured_midi to see what it sent. Non-blocking.

        Returns:
            dict: Whether capture started, and what to do next.
        """
        if not midi.start_capture():
            return {
                "error": "could not open a MIDI input port",
                "ports": midi.list_ports(),
            }
        return {
            "capturing": True,
            "next": "move a control on the Digitone, then call "
            "get_captured_midi",
        }

    @mcp.tool()
    def get_captured_midi(stop: bool = False) -> dict:
        """
        Show what the Digitone has sent since capture started.

        Each CC is reported with its range of values and which parameters in
        the data maps claim that CC number, so an unrecognised control shows
        up as a CC with an empty 'maps_to'.

        Args:
            stop (bool): Also stop capturing.

        Returns:
            dict: Aggregated control changes, NRPN sequences, notes, program
            changes and SysEx.
        """
        events = midi.stop_capture() if stop else midi.captured
        result = _summarise(events)
        result["capturing"] = not stop
        return result

    @mcp.tool()
    def stop_midi_capture() -> dict:
        """
        Stop recording MIDI and return everything captured.

        Returns:
            dict: Aggregated summary of the whole capture.
        """
        result = _summarise(midi.stop_capture())
        result["capturing"] = False
        return result

    @mcp.tool()
    def listen_for_midi(seconds: float = 5.0) -> dict:
        """
        Capture MIDI for a fixed window and report what arrived.

        Blocks for `seconds`, so the control has to be moved during that
        window. For anything interactive prefer start_midi_capture plus
        get_captured_midi, which does not race the user.

        Args:
            seconds (float): How long to listen, 0.5-60.

        Returns:
            dict: Aggregated summary of what was captured.
        """
        seconds = max(0.5, min(60.0, seconds))
        if not midi.start_capture():
            return {
                "error": "could not open a MIDI input port",
                "ports": midi.list_ports(),
            }
        time.sleep(seconds)
        result = _summarise(midi.stop_capture())
        result["listened_seconds"] = seconds
        return result

    @mcp.tool()
    def identify_cc(cc: int) -> dict:
        """
        Look up which parameters use a given CC number.

        Args:
            cc (int): Control Change number, 0-127.

        Returns:
            dict: Every section parameter mapped to that CC.
        """
        matches = _known_cc().get(cc, [])
        return {
            "cc": cc,
            "maps_to": matches,
            "note": "a CC used by several sections is normal: the Digitone "
            "reuses page slots across machines" if len(matches) > 1 else None,
        }
