"""The Digitone's Cirklon definitions, and what they have to get right.

Two things make one definition impossible. The four SYN machines share
CC 40 to 77 and only the meaning changes, and the six filter machines do
the same with CC 16 to 24 -- so a definition names one of each. And the
send effects answer on the FX control channel, where their CC numbers are
free to repeat the track's, so they need a definition of their own.
"""

import json
import os
import subprocess
import sys

import pytest

from elektron_mcp.digitone.data.sections import (
    CKI_LABELS, FX_CHANNEL_SECTIONS, SECTIONS,
)
from rig_midi.cirklon import LABEL_MAX, check_labels

CORPUS = os.path.join(os.path.dirname(__file__), "..", "..",
                      "CirklonSynthDefs")
FILES = ("Digitone2-FMTone.cki", "Digitone2-FMDrum.cki",
         "Digitone2-Wavetone.cki", "Digitone2-Swarmer.cki",
         "Digitone2-SendFX.cki")


def _present():
    return os.path.exists(os.path.join(CORPUS, FILES[0]))


def test_every_label_fits_the_display():
    assert check_labels(SECTIONS) == []


def test_the_label_table_only_names_real_parameters():
    """A typo here would silently leave a long label in place."""
    missing = []
    for key in CKI_LABELS:
        section, _, ident = key.partition(".")
        if ident not in SECTIONS.get(section, {}):
            missing.append(key)
    assert missing == []


def test_short_labels_came_from_the_manual_where_it_gives_them():
    """Appendix A shows RSET, SR.RT, OD.RT and ENV; this map had stored
    longer descriptive forms instead."""
    assert CKI_LABELS["amp.env_rset"] == "RSET"
    assert CKI_LABELS["fx.sr_rt"] == "SR.RT"
    assert CKI_LABELS["fx.od_rt"] == "OD.RT"
    assert CKI_LABELS["filter_multi_mode.env_depth"] == "ENV"
    assert CKI_LABELS["fm_drum.tune"] == "TUNE"


@pytest.mark.skipif(not _present(), reason="CirklonSynthDefs not alongside")
@pytest.mark.parametrize("filename", FILES)
def test_definitions_are_usable(filename):
    with open(os.path.join(CORPUS, filename), encoding="utf-8") as handle:
        data = json.load(handle)["instrument_data"]
    for name, inst in data.items():
        assert len(name) <= 16, name
        labels = [spec["label"] for spec in inst["CC_defs"].values()]
        assert all(len(label) <= LABEL_MAX for label in labels), name
        # No two rows may read the same, or the track page is ambiguous.
        assert len(labels) == len(set(labels)), (
            name, sorted(x for x in labels if labels.count(x) > 1)
        )


@pytest.mark.skipif(not _present(), reason="CirklonSynthDefs not alongside")
def test_a_machine_definition_leads_with_its_own_syn_page():
    """The track page should read as the device's SYN page 1 does."""
    path = os.path.join(CORPUS, "Digitone2-FMDrum.cki")
    with open(path, encoding="utf-8") as handle:
        inst = json.load(handle)["instrument_data"]["DN2 FM Drum"]
    page = [inst["track_values"][f"slot_{i}"] for i in range(1, 9)]
    assert [s["MIDI_CC"] for s in page] == list(range(40, 48))
    assert [s["label"] for s in page] == [
        "TUNE", "STIM", "SDEP", "ALGO", "OP.C", "OP.AB", "FDBK", "FOLD",
    ]


@pytest.mark.skipif(not _present(), reason="CirklonSynthDefs not alongside")
def test_the_send_fx_definition_is_on_the_fx_control_channel():
    """Not a track's. Their CC numbers repeat the track's -- the chorus and
    the machines both claim CC 70 -- so they cannot share a definition."""
    path = os.path.join(CORPUS, "Digitone2-SendFX.cki")
    with open(path, encoding="utf-8") as handle:
        inst = json.load(handle)["instrument_data"]["DN2 Send FX"]
    assert inst["midi_chan"] == 9

    chorus = {int(s["cc_msb"]) for s in SECTIONS["send_chorus"].values()}
    machine = {int(s["cc_msb"]) for s in SECTIONS["fm_tone"].values()}
    assert chorus & machine
    assert set(FX_CHANNEL_SECTIONS) <= set(SECTIONS)


@pytest.mark.skipif(not _present(), reason="CirklonSynthDefs not alongside")
def test_generated_definitions_are_up_to_date():
    script = os.path.join(os.path.dirname(__file__), "..", "tools",
                          "export_digitone_cki.py")
    done = subprocess.run([sys.executable, script, CORPUS, "--check"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
