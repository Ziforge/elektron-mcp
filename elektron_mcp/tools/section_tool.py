"""
Batch parameter tools, one per Digitone II section.

Every section in `SECTIONS` gets a single `set_<section>` tool taking the
track plus one optional argument per parameter. A patch is therefore one tool
call rather than thirty, which matters when designing a sound: the whole set
of values lands together instead of drifting in one CC at a time.

Tool signatures are generated from the parameter maps, so a parameter added to
`elektron_mcp/digitone/data/` shows up as an argument with no edit here.

Each tool takes values either as raw MIDI (0-127) or in the units shown on the
device -- `units="display"` turns tune=+24 into the right CC value using the
ranges already carried in the data maps -- and can send over 14-bit NRPN
instead of 7-bit CC where finer resolution matters.
"""

from typing import Optional

from elektron_mcp.digitone.data.sections import SECTIONS, MACHINE_SECTIONS
from elektron_mcp.patches.store import TRACK_STATE

# Extra guidance per section, merged in by register_section_tools so a second
# device can explain its own quirks (which channel to use, what is machine
# dependent) without this module knowing about that device.
SECTION_NOTES: dict[str, str] = {}

MACHINE_NOTE = {
    "fm_drum": "FM DRUM",
    "fm_tone": "FM TONE",
    "swarmer": "SWARMER",
    "wavetone": "WAVETONE",
}


def _nrpn_pair(spec: dict):
    """The NRPN (MSB, LSB) for a parameter, or None.

    The field names in the data files are inverted with respect to their
    meaning: `nrpn_lsb` holds the parameter bank, which the manual lists as
    the NRPN MSB, and `nrpn_msb` holds the parameter number, which is the
    LSB. Appendix C of the Digitone II manual gives LFO 3 Speed as MSB 1,
    LSB 58, and the data for it reads nrpn_lsb 1, nrpn_msb 58. Renaming the
    fields would touch every map, so the correction lives here.
    """
    if "nrpn_msb" not in spec or "nrpn_lsb" not in spec:
        return None
    return int(spec["nrpn_lsb"]), int(spec["nrpn_msb"])


def _describe(ident: str, spec: dict) -> str:
    """One docstring line for a parameter: how it is addressed and its
    display range."""
    if "cc_msb" in spec:
        bits = [f"CC {spec['cc_msb']}"]
    else:
        pair = _nrpn_pair(spec)
        bits = [f"NRPN {pair[0]}:{pair[1]}" if pair else "no CC or NRPN"]

    lo, hi = spec.get("min_val", 0), spec.get("max_val", 127)
    if (lo, hi) != (0, 127):
        bits.append(f"displays {lo} to {hi}")

    options = spec.get("options")
    if options:
        names = options if isinstance(options, list) else list(options)
        shown = ", ".join(str(o) for o in names[:8])
        if len(names) > 8:
            shown += f", ... ({len(names)} total, see get_param_reference)"
        bits.append(f"options: {shown}")

    default = spec.get("default")
    if default is not None:
        bits.append(f"default {default}")

    label = spec.get("_label", ident)
    return f"        {ident} (number): {label} -- {', '.join(bits)}."


def _build_docstring(section: str, params: dict) -> str:
    head = f"Set any number of {section} parameters on one track in a single call."

    pre = ""
    if section in SECTION_NOTES:
        pre = f"\n    {SECTION_NOTES[section]}\n"
    elif section in MACHINE_SECTIONS:
        pre = (
            f"\n    Requires the track's machine to be set to {MACHINE_NOTE[section]} "
            "on the device first; machine selection has no MIDI CC. Sending these "
            "to a track running a different machine will move whatever parameters "
            "share those CC numbers.\n"
        )
    elif section.startswith("filter_"):
        pre = (
            "\n    Requires this filter type to be selected on the track's FLTR "
            "page for these to land as named.\n"
        )

    lines = [
        head,
        pre,
        "    Omitted parameters are left alone.",
        "",
        "    Args:",
        "        track (int): Digitone track / MIDI channel, 1-16.",
    ]
    lines += [_describe(i, s) for i, s in params.items()]
    lines += [
        "        units (str): 'midi' (default) treats values as raw 0-127.",
        "            'display' treats them as the numbers shown on the device",
        "            and scales them, so tune=24 means +24 semitones.",
        "        use_nrpn (bool): Send over 14-bit NRPN instead of 7-bit CC for",
        "            finer resolution. Values are still given in the same units.",
        "",
        "    Returns:",
        "        dict: 'sent' maps each parameter to the MIDI value delivered,",
        "        'failed' lists parameters that could not be sent, and",
        "        'out_of_range' lists display values outside the parameter's range.",
    ]
    return "\n".join(lines)


def to_midi_value(spec: dict, value) -> tuple[Optional[int], Optional[str]]:
    """Convert a display-unit value to a raw MIDI value.

    Returns (midi_value, error). Enum parameters accept their option name.
    """
    options = spec.get("options")
    if isinstance(options, dict) and isinstance(value, str):
        if value not in options:
            return None, f"unknown option {value!r}"
        return max(0, min(127, int(options[value]))), None

    if isinstance(value, str):
        return None, f"expected a number, got {value!r}"

    lo = spec.get("min_val", 0)
    hi = spec.get("max_val", 127)
    lo_midi = spec.get("min_midi", 0)
    hi_midi = spec.get("max_midi", 127)

    if isinstance(lo, list) or isinstance(hi, list):
        return None, "parameter has a list-valued range; use units='midi'"

    if hi == lo:
        return int(lo_midi), None
    if not lo <= value <= hi:
        return None, f"{value} outside display range {lo} to {hi}"

    frac = (value - lo) / (hi - lo)
    return int(round(lo_midi + frac * (hi_midi - lo_midi))), None


def _send(midi, spec: dict, track: int, midi_value: int, use_nrpn: bool) -> bool:
    pair = _nrpn_pair(spec)
    has_cc = "cc_msb" in spec

    # Some parameters have no CC at all. The Digitone II's LFO 3 is the
    # case: Appendix C.8 leaves its CC column empty and lists only NRPN,
    # so for those there is nothing to degrade to.
    if pair and (use_nrpn or not has_cc):
        # NRPN is 14-bit; scale the 7-bit value up so the two paths agree.
        if midi.send_nrpn(track, pair[0], pair[1], midi_value << 7):
            return True
        if not has_cc:
            return False
        # Fall back rather than fail: not every parameter answers to NRPN.

    # Not every parameter map carries NRPN numbers -- maps transcribed from
    # Cirklon instrument definitions have CC only -- so an NRPN request
    # degrades to CC when the map cannot honour it.
    if not has_cc:
        return False
    return midi.send_cc(track, int(spec["cc_msb"]), midi_value)


ALL_SECTIONS: dict[str, dict] = dict(SECTIONS)


def _apply(
    midi,
    section: str,
    track: int,
    values: dict,
    units: str = "midi",
    use_nrpn: bool = False,
) -> dict:
    params = ALL_SECTIONS[section]

    if not 1 <= track <= 16:
        return {"error": f"track must be 1-16, got {track}", "sent": {}, "failed": []}
    if units not in ("midi", "display"):
        return {"error": f"units must be 'midi' or 'display', got {units!r}"}

    sent, failed, out_of_range = {}, [], {}
    for ident, value in values.items():
        if value is None:
            continue
        spec = params[ident]

        if units == "display":
            midi_value, error = to_midi_value(spec, value)
            if error:
                out_of_range[ident] = error
                continue
        else:
            midi_value = max(0, min(127, int(round(float(value)))))

        if _send(midi, spec, track, midi_value, use_nrpn):
            sent[ident] = midi_value
        else:
            failed.append(ident)

    if sent:
        TRACK_STATE.record(track, section, sent)

    result = {"section": section, "track": track, "sent": sent, "failed": failed}
    if out_of_range:
        result["out_of_range"] = out_of_range
    if not sent and not failed and not out_of_range:
        result["note"] = "no parameters supplied; nothing was sent"
    return result


def apply_sections(
    midi, track: int, sections: dict, use_nrpn: bool = False
) -> dict:
    """Send a whole multi-section snapshot to a track. Used by patch recall."""
    summary = {"track": track, "sections": {}, "unknown": {}}
    for section, values in sections.items():
        if section not in ALL_SECTIONS:
            summary["unknown"][section] = "unknown section"
            continue
        known = {k: v for k, v in values.items() if k in ALL_SECTIONS[section]}
        unknown = sorted(set(values) - set(known))
        if unknown:
            summary["unknown"][section] = unknown
        summary["sections"][section] = _apply(
            midi, section, track, known, "midi", use_nrpn
        )
    return summary


def _make_tool(midi, section: str, params: dict):
    """Generate a real function with one optional argument per parameter.

    The MCP server derives the tool schema from the signature, so the arguments are
    compiled rather than hidden behind **kwargs -- that is what makes them
    visible and individually documented to the model.
    """
    args = ", ".join(f"{ident}: Optional[float] = None" for ident in params)
    mapping = ", ".join(f"{ident!r}: {ident}" for ident in params)

    src = (
        f"def set_{section}(track: int, {args}, units: str = 'midi',"
        f" use_nrpn: bool = False) -> dict:\n"
        f"    {_build_docstring(section, params)!r}\n"
        f"    return _apply(_midi, {section!r}, track, {{{mapping}}},"
        f" units, use_nrpn)\n"
    )

    namespace = {"Optional": Optional, "_apply": _apply, "_midi": midi}
    exec(src, namespace)
    return namespace[f"set_{section}"]


def register_section_tools(mcp, midi, sections: dict | None = None,
                           notes: dict | None = None):
    """Register one batch parameter tool per section with the MCP server.

    Args:
        mcp: The MCP server instance.
        midi: The MIDI interface.
        sections: Parameter registry to expose. Defaults to the Digitone II
            sections; another device passes its own.
        notes: Optional {section: guidance} merged into tool docstrings.
    """
    registry = SECTIONS if sections is None else sections
    if notes:
        SECTION_NOTES.update(notes)
    ALL_SECTIONS.update(registry)
    for section, params in registry.items():
        mcp.tool()(_make_tool(midi, section, params))


def register_enum_tool(mcp, midi):
    """Register the named-option tool.

    Separate from register_section_tools because that is called once per
    device, and registering this inside it produced a duplicate tool name --
    silently tolerated by MCP SDK 1.x and warned about by 2.x.
    """

    @mcp.tool()
    def set_enum_parameter(section: str, track: int, parameter: str,
                           option: str) -> dict:
        """
        Set a parameter that takes a named option rather than a number.

        Covers things like filter type, LFO waveform and trig mode, LFO
        destination and the FX routing switches. Call get_param_reference to
        see the option names for a section.

        Args:
            section (str): Section name, e.g. 'filter_multi_mode', 'lfo1'.
            track (int): Digitone track / MIDI channel, 1-16.
            parameter (str): Parameter identifier within the section.
            option (str): Option name as listed by get_param_reference.

        Returns:
            dict: The value sent, or the available options on failure.
        """
        if section not in ALL_SECTIONS:
            return {"error": f"unknown section {section!r}",
                    "available": sorted(ALL_SECTIONS)}
        if parameter not in ALL_SECTIONS[section]:
            return {"error": f"{section} has no parameter {parameter!r}",
                    "available": sorted(ALL_SECTIONS[section])}

        spec = ALL_SECTIONS[section][parameter]
        options = spec.get("options")
        if not isinstance(options, dict):
            return {
                "error": f"{section}.{parameter} has no named options; "
                "use the section tool with a numeric value"
            }
        return _apply(midi, section, track, {parameter: option}, "display", False)
