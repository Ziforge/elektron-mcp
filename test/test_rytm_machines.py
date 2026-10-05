"""The Rytm's per-machine SYNTH names, and their Cirklon export.

Every machine drives CC 16-23, but each names them differently, so a single
instrument definition cannot describe the Rytm. These pin the machine table
against the manual's own structure and keep the generated definitions in
step with it.
"""

import json
import os
import subprocess
import sys

import pytest

from elektron_mcp.rytm.machines import (
    FAMILIES, MACHINES, display_name, family,
)
from rig_midi.cirklon import LABEL_MAX

CORPUS = os.path.join(os.path.dirname(__file__), "..", "..",
                      "CirklonSynthDefs")
# The Cirklon truncates instrument names at 16 characters -- two names in
# the committed corpus are cut at exactly that.
NAME_MAX = 16


def test_every_machine_in_the_manual_is_present():
    """Appendix C.8 lists 32 machines."""
    assert len(MACHINES) == 32


def test_machines_use_a_contiguous_run_of_ccs_from_16():
    """The eight SYNTH CCs are 16 to 23. Not every machine uses all eight
    -- UT IMPULSE has four, CH METALLIC three -- but none skips one."""
    for machine, (_, params) in MACHINES.items():
        ccs = [cc for cc, _, _ in params]
        assert ccs == list(range(16, 16 + len(ccs))), machine
        assert 3 <= len(ccs) <= 8, machine


def test_labels_fit_the_cirklon_display():
    for machine, (_, params) in MACHINES.items():
        for cc, full, label in params:
            assert 0 < len(label) <= LABEL_MAX, (machine, full, label)


def test_no_machine_shows_the_same_label_twice():
    """The device itself can show DEC for two oscillators and distinguish
    them by position; the Cirklon keys its table by CC and cannot, so each
    label has to be unique within a machine."""
    for machine, (_, params) in MACHINES.items():
        labels = [label for _, _, label in params]
        assert len(labels) == len(set(labels)), (machine, labels)


def test_instrument_names_are_unique_and_fit():
    names = [display_name(m) for m in MACHINES]
    assert len(names) == len(set(names))
    for name in names:
        assert len(name) <= NAME_MAX, (name, len(name))


def test_every_machine_belongs_to_a_known_family():
    for machine in MACHINES:
        assert family(machine) in set(FAMILIES.values())
    assert len({family(m) for m in MACHINES}) == 13


def test_the_tom_machine_covers_three_tracks():
    """Appendix C names it "LT, MT, HT CLASSIC" -- one machine shared by
    the low, mid and high tom tracks."""
    assert "LT, MT, HT CLASSIC" in MACHINES
    assert family("LT, MT, HT CLASSIC") == "Tom"
    assert display_name("LT, MT, HT CLASSIC") == "Rytm Tom Classic"


def test_appendix_c_and_d_naming_drift_is_resolved():
    """The MIDI appendix and the machine appendix sometimes name the same
    parameter differently. These are the cases where the label had to be
    matched by meaning rather than by string."""
    labels = {full: label for _, params in MACHINES.values()
              for _, full, label in params}
    assert labels["Transient Tick"] == "TIC"
    assert labels["Body Decay"] == "BDY"
    assert labels["Snap Type"] == "SNP"
    assert labels["LP Frequency"] == "LPF"
    assert labels["Tune Osc 1"] == "T1"
    assert labels["Waveform 1"] == "WAV1"
    assert labels["Tune 1"] == "OSC1"
    assert labels["Component 1"] == "C1"


def _corpus_present():
    return os.path.exists(os.path.join(CORPUS, "RytmMKII.cki"))


@pytest.mark.skipif(not _corpus_present(),
                    reason="CirklonSynthDefs not checked out alongside")
def test_generated_definitions_are_up_to_date():
    """Running the exporter must not change what is committed."""
    script = os.path.join(os.path.dirname(__file__), "..", "tools",
                          "export_rytm_cki.py")
    done = subprocess.run([sys.executable, script, CORPUS, "--check"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "up to date" in done.stdout


@pytest.mark.skipif(not _corpus_present(),
                    reason="CirklonSynthDefs not checked out alongside")
def test_each_family_file_holds_its_machines():
    for machine in MACHINES:
        path = os.path.join(CORPUS, f"RytmMKII-{family(machine)}.cki")
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)["instrument_data"]
        assert display_name(machine) in data, machine


@pytest.mark.skipif(not _corpus_present(),
                    reason="CirklonSynthDefs not checked out alongside")
def test_a_generated_definition_names_the_machines_own_parameters():
    """BD HARD's track page should read as the device's own screen does."""
    path = os.path.join(CORPUS, "RytmMKII-BD.cki")
    with open(path, encoding="utf-8") as handle:
        inst = json.load(handle)["instrument_data"]["Rytm BD Hard"]
    page = [inst["track_values"][f"slot_{i}"] for i in range(1, 9)]
    assert [s["MIDI_CC"] for s in page] == list(range(16, 24))
    assert [s["label"] for s in page] == ["LEV", "TUN", "DEC", "HLD",
                                          "SWT", "SWD", "WAV", "TIC"]
    # The shared drum-track parameters come too, so the definition stands
    # on its own.
    assert len(inst["CC_defs"]) == 59
    assert inst["CC_defs"]["CC_3"]["label"] == "Note"
