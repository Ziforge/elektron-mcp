#!/usr/bin/env python3
"""
Generate Cirklon instrument definitions for the Analog Rytm MKII.

The Rytm's eight SYNTH CCs mean different things on every machine, so one
definition cannot describe it. This writes one definition per machine,
grouped into a file per track-type family, plus a regenerated drum-track,
FX and performance definition.

    uv run python tools/export_rytm_cki.py ../CirklonSynthDefs

Pass --check to compare against what is already there without writing,
which is what the test suite does.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from elektron_mcp.rytm.data import RYTM_SECTIONS            # noqa: E402
from elektron_mcp.rytm.machines import MACHINES, display_name, family  # noqa: E402,E501
from rig_midi.cirklon import build_instrument, to_cki        # noqa: E402

# The drum tracks, the FX block and the performance macros sit on separate
# MIDI channels and reuse each other's CC numbers, so each is its own
# instrument rather than one big definition.
DRUM_SECTIONS = ("rytm_trig", "rytm_track", "rytm_euclid", "rytm_synth",
                 "rytm_sample", "rytm_filter", "rytm_amp", "rytm_lfo")

# A drum track's page leads with the machine's own parameters, since those
# are what differ per machine and what you reach for. Machines with fewer
# than eight leave room, filled from here in order.
FILLER_SLOTS = ("rytm_amp.vol", "rytm_filter.freq", "rytm_filter.reso",
                "rytm_amp.dec", "rytm_amp.delay_send",
                "rytm_amp.reverb_send", "rytm_amp.pan",
                "rytm_amp.overdrive")
SLOT_COUNT = 8


def drum_sections():
    return {k: RYTM_SECTIONS[k] for k in DRUM_SECTIONS}


def machine_instrument(machine, midi_chan=1):
    """A drum-track definition with one machine's SYNTH names applied."""
    sections = {k: dict(v) for k, v in drum_sections().items()}
    _, params = MACHINES[machine]

    synth = {}
    for cc, full, label in params:
        ident = full.lower().replace(" ", "_").replace("/", "_")
        synth[ident] = {"cc_msb": cc, "_label": label, "_page": machine}
    # Track Machine stays reachable: it is how the machine gets selected
    # over MIDI in the first place.
    synth["trk_mch"] = dict(RYTM_SECTIONS["rytm_synth"]["trk_mch"])
    sections["rytm_synth"] = synth

    slots = [f"rytm_synth.{i}" for i in synth if i != "trk_mch"]
    slots += [s for s in FILLER_SLOTS if s not in slots]
    return build_instrument(sections, midi_port=1, midi_chan=midi_chan,
                            slots=slots[:SLOT_COUNT], multi=True)


def build_all():
    """Return {filename: {instrument name: definition}}."""
    files = {}
    for machine in MACHINES:
        fam = family(machine)
        name = display_name(machine)
        files.setdefault(f"RytmMKII-{fam}.cki", {})[name] = \
            machine_instrument(machine)
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="CirklonSynthDefs checkout")
    ap.add_argument("--check", action="store_true",
                    help="report differences instead of writing")
    args = ap.parse_args()

    problems = []
    for filename, instruments in sorted(build_all().items()):
        path = os.path.join(args.target, filename)
        text = to_cki(instruments)
        if args.check:
            if not os.path.exists(path):
                problems.append(f"{filename}: missing")
            elif open(path, encoding="utf-8").read() != text:
                problems.append(f"{filename}: differs")
            continue
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"  {filename}: {len(instruments)} machines, "
              f"{len(text)} bytes")

    if args.check:
        for line in problems:
            print(f"  {line}")
        print("up to date" if not problems else f"{len(problems)} stale")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
