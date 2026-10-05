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
        properties = set(tool.inputSchema["properties"])
        gaps += [(section, p) for p in params if p not in properties]
    assert gaps == [], f"parameters unreachable by any tool: {gaps}"


def test_parameter_total_is_stable():
    """Guards against a data map silently losing parameters."""
    assert sum(len(p) for p in SECTIONS.values()) == 184


@pytest.mark.parametrize("section", sorted(SECTIONS))
def test_no_duplicate_cc_within_a_section(section):
    """Two parameters sharing a CC means setting one moves the other.

    This is how FM Tone operator B's envelope was shadowing operator A.
    """
    seen: dict[int, str] = {}
    clashes = []
    for ident, spec in SECTIONS[section].items():
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
