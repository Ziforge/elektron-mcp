"""
Analog Rytm MKII coverage.

The map is transcribed from Cirklon instrument definitions and has not been
verified against the hardware, so these tests check what can be checked
without it: that every parameter is reachable, that no two parameters in a
section share a CC, and that the CC-only map does not break the NRPN path.
"""

import asyncio
import keyword

import pytest

from elektron_mcp.rytm.data import RYTM_SECTIONS, RYTM_CHANNELS, RYTM_NOTES
from elektron_mcp.tools import section_tool


class FakeMidi:
    def __init__(self):
        self.ccs, self.nrpns = [], []

    def send_cc(self, channel, cc, value):
        self.ccs.append((channel, cc, value))
        return True

    def send_nrpn(self, channel, msb, lsb, value):
        self.nrpns.append((channel, msb, lsb, value))
        return True


def _tools():
    from elektron_mcp.mcp_server.server import mcp

    return {t.name: t for t in asyncio.run(mcp.list_tools())}


def test_every_rytm_parameter_is_reachable():
    tools = _tools()
    gaps = []
    for section, params in RYTM_SECTIONS.items():
        tool = tools.get(f"set_{section}")
        assert tool is not None, f"no tool registered for {section}"
        props = set(tool.input_schema["properties"])
        gaps += [(section, p) for p in params if p not in props]
    assert gaps == [], f"unreachable Rytm parameters: {gaps}"


def test_rytm_parameter_total_is_stable():
    """96 originally, plus the three trig parameters -- note, velocity and
    length, CC 3 to 5 -- that Appendix C of the manual lists and the
    transcription from the .cki files had missed."""
    assert sum(len(p) for p in RYTM_SECTIONS.values()) == 99


def test_trig_parameters_cover_note_velocity_and_length():
    """Without these a sequencer can shape a track but not play it."""
    trig = RYTM_SECTIONS["rytm_trig"]
    assert [trig[k]["cc_msb"] for k in ("note", "velocity", "length")] \
        == [3, 4, 5]


def test_lfo_depth_is_the_one_high_resolution_parameter():
    """Appendix C.6: "the LFO depth is a high-resolution parameter, with CC
    LSB value" -- CC 109 coarse, CC 118 fine. Nothing else on the Rytm
    declares a CC LSB."""
    lfo = RYTM_SECTIONS["rytm_lfo"]
    assert lfo["depth"]["cc_lsb"] == 118
    fine = [ident for section in RYTM_SECTIONS.values()
            for ident, spec in section.items() if "cc_lsb" in spec]
    assert fine == ["depth"]


@pytest.mark.parametrize("section", sorted(RYTM_SECTIONS))
def test_no_duplicate_cc_within_a_rytm_section(section):
    seen, clashes = {}, []
    for ident, spec in RYTM_SECTIONS[section].items():
        cc = int(spec["cc_msb"])
        if cc in seen:
            clashes.append((cc, seen[cc], ident))
        seen[cc] = ident
    assert clashes == [], f"{section} parameters share a CC: {clashes}"


@pytest.mark.parametrize("section", sorted(RYTM_SECTIONS))
def test_rytm_identifiers_are_usable(section):
    for ident in RYTM_SECTIONS[section]:
        assert ident.isidentifier() and not keyword.iskeyword(ident)


def test_rytm_does_not_collide_with_digitone_section_names():
    from elektron_mcp.digitone.data.sections import SECTIONS

    assert not (set(SECTIONS) & set(RYTM_SECTIONS))


def test_nrpn_request_degrades_to_cc_on_a_cc_only_map():
    """Regression: the map has no NRPN numbers, and the NRPN path indexed
    spec["nrpn_msb"] unconditionally, so asking for NRPN would raise."""
    midi = FakeMidi()
    out = section_tool._apply(
        midi, "rytm_synth", 3, {"syn1": 64}, use_nrpn=True
    )
    assert out["sent"] == {"syn1": 64}
    assert midi.nrpns == []
    assert midi.ccs == [(3, 16, 64)]


def test_machine_is_settable_over_midi_on_the_rytm():
    """Unlike the Digitone II, machine selection here is just a CC."""
    midi = FakeMidi()
    section_tool._apply(midi, "rytm_synth", 1, {"trk_mch": 5})
    assert midi.ccs == [(1, 15, 5)]


def test_section_notes_reach_the_tool_description():
    tools = _tools()
    assert "machine dependent" in tools["set_rytm_synth"].description
    assert "channel 13" in tools["set_rytm_fx"].description


def test_fixed_channel_sections_are_documented():
    assert RYTM_CHANNELS["rytm_fx"] == 13
    assert RYTM_CHANNELS["rytm_perf"] == 14
    assert set(RYTM_CHANNELS) <= set(RYTM_SECTIONS)
    assert set(RYTM_NOTES) <= set(RYTM_SECTIONS)
