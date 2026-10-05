"""
Coverage and data-integrity gates for the Digitone parameter surface.

These guard the two failure modes that were live in this repo: parameters that
exist in the data maps but are reachable by no tool, and two parameters
sharing one CC number so setting one silently moves the other.
"""

import asyncio
import keyword

import pytest

from elektron_mcp.digitone.config.config import digitone_config
from elektron_mcp.digitone.data.sections import SECTIONS, to_identifier


def _tools():
    from elektron_mcp.mcp_server.server import mcp

    return {t.name: t for t in asyncio.run(mcp.list_tools())}


def test_every_parameter_is_reachable_by_a_tool():
    """All 184 parameters must appear as an argument of their section tool."""
    tools = _tools()
    gaps = []
    for section, params in SECTIONS.items():
        tool = tools.get(f"set_{section}")
        assert tool is not None, f"no tool registered for section {section}"
        properties = set(tool.input_schema["properties"])
        gaps += [(section, p) for p in params if p not in properties]
    assert gaps == [], f"parameters unreachable by any tool: {gaps}"


def test_parameter_total_is_stable():
    """Guards against a data map silently losing parameters.

    184 for a long while, which turned out to be five of Appendix C's
    eleven subsections. The trig, track and euclidean parameters, the whole
    send-effects and mixer block, and the master overdrive were all absent.
    """
    assert sum(len(p) for p in SECTIONS.values()) == 244


@pytest.mark.parametrize("section", sorted(SECTIONS))
def test_no_duplicate_cc_within_a_section(section):
    """Two parameters sharing a CC means setting one moves the other.

    This is how FM Tone operator B's envelope was shadowing operator A.
    """
    seen: dict[int, str] = {}
    clashes = []
    for ident, spec in SECTIONS[section].items():
        if "cc_msb" not in spec:
            continue  # NRPN-only: nothing to clash with.
        cc = int(spec["cc_msb"])
        if cc in seen:
            clashes.append((cc, seen[cc], ident))
        seen[cc] = ident
    assert clashes == [], f"{section} has parameters sharing a CC: {clashes}"


@pytest.mark.parametrize("section", sorted(SECTIONS))
def test_identifiers_are_usable_in_a_signature(section):
    """Tool arguments are generated into real function signatures."""
    for ident in SECTIONS[section]:
        assert ident.isidentifier(), f"{section}.{ident} is not an identifier"
        assert not keyword.iskeyword(ident), f"{section}.{ident} is a keyword"


def test_fm_tone_operator_b_envelope_has_its_own_ccs():
    """Regression: operator B duplicated A's CC 48-51 instead of using 52-55.

    SYN2 page slots P2A..P2H are CC 48..55, so A owns 48-51 and B owns 52-55.
    """
    page = digitone_config.fmtone.pages["page_2"].parameters
    a = [int(page[f"A.{p}"].midi.cc_msb) for p in ("atk", "dec", "end", "lev")]
    b = [int(page[f"B.{p}"].midi.cc_msb) for p in ("atk", "dec", "end", "lev")]
    assert a == [48, 49, 50, 51]
    assert b == [52, 53, 54, 55]


def test_nested_parameters_resolve_by_dotted_key():
    """Regression: controllers address nested params as "A.atk", but only the
    nested group was registered, so every nested setter raised."""
    for page_name, keys in (
        ("page_2", ("A.atk", "A.dec", "A.end", "A.lev",
                    "B.atk", "B.dec", "B.end", "B.lev")),
        ("page_4", ("Ratio_Offset.C", "Ratio_Offset.A", "Ratio_Offset.B1",
                    "Ratio_Offset.B2", "Key_Track.A", "Key_Track.B1",
                    "Key_Track.B2")),
    ):
        params = digitone_config.fmtone.pages[page_name].parameters
        for key in keys:
            assert key in params, f"{page_name} missing dotted key {key}"


def test_to_identifier_rules():
    assert to_identifier("OP.AB") == "op_ab"
    assert to_identifier("TYPE(lowpass/highpass)") == "type"
    assert to_identifier("Env. RSET") == "env_rset"
    assert to_identifier("DEL") == "del_"


def test_play_and_reference_tools_registered():
    """A patch you cannot trigger cannot be judged."""
    tools = _tools()
    for name in ("play_note", "play_sequence", "hold_note", "release_note",
                 "all_notes_off", "set_program", "list_sections",
                 "get_param_reference"):
        assert name in tools, f"{name} not registered"


def test_lfo_destination_enum_is_shared_across_lfos():
    """LFO1 and LFO2 agree on every destination they share, which is why
    LFO3 can inherit the enumeration rather than needing its own."""
    from elektron_mcp.digitone.data.lfo import (
        LFO1_PARAMS, LFO2_PARAMS, LFO3_PARAMS,
    )

    o1 = LFO1_PARAMS["DEST"]["options"]
    o2 = LFO2_PARAMS["DEST"]["options"]
    o3 = LFO3_PARAMS["DEST"]["options"]

    assert [k for k in o1 if k in o2 and o1[k] != o2[k]] == []
    assert o3 and all(0 <= v <= 127 for v in o3.values())
    # LFO1's own parameters are addressable as destinations at their LFO page
    # slot index, with slot 4 (DEST itself) excluded.
    assert sorted(v for k, v in o3.items() if k.startswith("lfo1_")) == [
        1, 2, 3, 5, 6, 7, 8
    ]


def test_lfo3_lfo2_targets_remain_an_explicit_gap():
    """Appendix D says LFO3 can target LFO2's parameters. Those values are
    not known, so they must stay absent rather than be guessed."""
    from elektron_mcp.digitone.data.lfo import LFO3_PARAMS

    o3 = LFO3_PARAMS["DEST"]["options"]
    assert [k for k in o3 if k.startswith("lfo2_")] == []


def test_no_parameter_uses_a_reserved_or_impossible_cc():
    """CC 120 to 127 are MIDI channel mode messages, not parameters.

    The Digitone II's LFO 3 carried invented CCs 121 to 128, continued from
    the LFO 1 and LFO 2 runs. The manual lists no CC for LFO 3 at all. Those
    numbers were not merely wrong: 123 is All Notes Off, so setting LFO 3
    FADE silenced the track, and 124 to 127 switch the device's MIDI mode.
    128 is not a valid CC, which is how a hardware sweep surfaced it.
    """
    offenders = []
    for section, params in SECTIONS.items():
        for ident, spec in params.items():
            if "cc_msb" not in spec:
                continue
            cc = int(spec["cc_msb"])
            if not 0 <= cc <= 119:
                offenders.append(f"{section}.{ident} = CC {cc}")
    assert offenders == [], f"reserved or impossible CCs: {offenders}"


def test_every_parameter_is_addressable_somehow():
    """By CC or by NRPN. A parameter with neither cannot be sent at all."""
    unreachable = [
        f"{section}.{ident}"
        for section, params in SECTIONS.items()
        for ident, spec in params.items()
        if "cc_msb" not in spec and "nrpn_msb" not in spec
    ]
    assert unreachable == []


def test_lfo3_is_nrpn_only_with_the_numbers_from_the_manual():
    """Appendix C.8: LFO 3 Speed is NRPN MSB 1, LSB 58, through Depth at
    LSB 72 -- note the jump from 62 to 70 between Waveform and Start
    Phase, which is in the manual too."""
    lfo3 = SECTIONS["lfo3"]
    assert all("cc_msb" not in spec for spec in lfo3.values())
    # The data files name these fields the other way round: nrpn_lsb holds
    # the bank, which the manual calls the MSB.
    assert [int(s["nrpn_msb"]) for s in lfo3.values()] == [
        58, 59, 60, 61, 62, 70, 71, 72,
    ]
    assert {int(s["nrpn_lsb"]) for s in lfo3.values()} == {1}


def test_declared_midi_range_covers_every_named_option():
    """An option the declared range excludes cannot be selected.

    The LFO destination parameters declared a 25 to 50 window while their
    own option table ran 0 to 99, so most destinations -- the whole AMP and
    FX half of Appendix D among them -- were unreachable, and a mid-range
    value landed on no destination at all. A hardware sweep found it: every
    LFO parameter except depth read as inaudible, because an LFO with no
    destination cannot make its speed or waveform heard.
    """
    offenders = []
    for section, params in SECTIONS.items():
        for ident, spec in params.items():
            options = spec.get("options")
            if not isinstance(options, dict) or not options:
                continue
            lo = spec.get("min_midi", 0)
            hi = spec.get("max_midi", 127)
            values = [int(v) for v in options.values()]
            if min(values) < lo or max(values) > hi:
                offenders.append(
                    f"{section}.{ident}: options {min(values)}-{max(values)} "
                    f"outside declared {lo}-{hi}"
                )
    assert offenders == [], "\n".join(offenders)


def test_appendix_c_subsections_are_all_represented():
    """Every parameter block the manual documents has a section here.

    The map covered only the machines, filter, amp, FX and LFOs for a long
    time -- five of Appendix C's eleven subsections. These are the others,
    named by where they live rather than by count, so a renamed section
    fails loudly instead of quietly shrinking the map.
    """
    expected = {
        "trig",         # C.2
        "track",        # C.1
        "euclid",       # C.6
        "misc",         # C.12, the per-track half
        "send_delay",   # C.9
        "send_reverb",  # C.9
        "send_chorus",  # C.9
        "compressor",   # C.10
        "external_in",  # C.10
        "master",       # C.12, the FX-channel half
    }
    assert expected <= set(SECTIONS)


def test_euclidean_sequencer_is_nrpn_only():
    """Appendix C.6 leaves the CC column empty for all seven, as it does
    for LFO 3."""
    euclid = SECTIONS["euclid"]
    assert len(euclid) == 7
    assert all("cc_msb" not in spec for spec in euclid.values())
    assert [int(s["nrpn_msb"]) for s in euclid.values()] == [
        8, 9, 10, 11, 12, 13, 14,
    ]


def test_fx_channel_sections_are_marked_as_such():
    """These are addressed on the FX CONTROL CH, not a track's channel.
    That is also why their CCs may collide with the per-track ones, so
    anything that sends a whole patch has to keep the two apart."""
    from elektron_mcp.digitone.data.sections import FX_CHANNEL_SECTIONS

    assert set(FX_CHANNEL_SECTIONS) <= set(SECTIONS)
    # The collision is real: the chorus and the source machines both use
    # CC 70, and the compressor and LFO 2 both use CC 111.
    chorus = {int(s["cc_msb"]) for s in SECTIONS["send_chorus"].values()}
    lfo2 = {int(s["cc_msb"]) for s in SECTIONS["lfo2"].values()}
    comp = {int(s["cc_msb"]) for s in SECTIONS["compressor"].values()}
    assert 70 in chorus
    assert comp & lfo2


def test_external_in_names_each_control_once():
    """Appendix C.10 lists every external input control twice -- as
    separate L and R controls and again as a linked pair -- on the same CC
    both times. Naming both would put two identifiers on one CC and make
    setting either move the other."""
    ccs = [int(s["cc_msb"]) for s in SECTIONS["external_in"].values()]
    assert len(ccs) == len(set(ccs))
