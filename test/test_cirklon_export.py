"""The Rytm map and its Cirklon definitions must stay in agreement.

The Rytm occupies three instrument definitions rather than one: the drum
tracks, the FX block and the performance macros sit on separate MIDI
channels and deliberately reuse each other's CC numbers. Comparing the
whole map against any one of them reports dozens of false differences, so
each role is checked against its own file.

Skipped when the CirklonSynthDefs checkout is not alongside this repo.
"""

import os

import pytest

from elektron_mcp.rytm.data import RYTM_SECTIONS
from rig_midi.cirklon import cc_collisions, check_labels, compare_cc_defs

CORPUS = os.path.join(os.path.dirname(__file__), "..", "..",
                      "CirklonSynthDefs")

DRUM = ("rytm_trig", "rytm_track", "rytm_euclid", "rytm_synth",
        "rytm_sample", "rytm_filter", "rytm_amp", "rytm_lfo")
ROLES = {
    "RytmMKII": DRUM,
    "RytmMKII-FX": ("rytm_fx",),
    "RytmMKII-Perf": ("rytm_perf",),
}


def _subset(keys):
    return {k: RYTM_SECTIONS[k] for k in keys}


@pytest.mark.parametrize("name", sorted(ROLES))
def test_cc_defs_match_the_committed_definition(name):
    path = os.path.join(CORPUS, f"{name}.cki")
    if not os.path.exists(path):
        pytest.skip("CirklonSynthDefs not checked out alongside")
    report = compare_cc_defs(_subset(ROLES[name]), path, name)
    assert report["only_in_map"] == []
    assert report["only_in_cki"] == []
    assert report["different"] == {}


@pytest.mark.parametrize("name", sorted(ROLES))
def test_each_role_is_internally_unambiguous(name):
    """Within one role no two parameters claim the same CC, which is what
    makes a single definition per role possible."""
    assert cc_collisions(_subset(ROLES[name])) == {}


@pytest.mark.parametrize("name", sorted(ROLES))
def test_labels_fit_the_cirklon_display(name):
    assert check_labels(_subset(ROLES[name])) == []


def test_the_drum_and_fx_roles_genuinely_collide():
    """26 CCs mean one thing on a drum track and another on the FX track.
    This is why they cannot share a definition -- and why an earlier
    whole-map comparison looked like drift when it was not."""
    clashes = cc_collisions(_subset(DRUM + ("rytm_fx",)))
    assert len(clashes) == 26
    assert 16 in clashes and 70 in clashes
