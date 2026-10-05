#!/usr/bin/env python3
"""
Generate Cirklon instrument definitions for the Digitone II.

Like the Rytm, the Digitone cannot be described by one definition, for two
separate reasons.

Its four SYN machines share CC 40 to 77 and only the meaning changes --
Appendix C.3 calls them "Data entry knob A-H (machine dependent)" -- so a
definition has to name one machine's parameters. Its six filter machines do
the same with CC 16 to 24.

And the send effects, mixer and master overdrive answer on the FX control
channel rather than a track's, which is why their CC numbers are free to
repeat the track's: the chorus and the machines both claim CC 70. Those get
their own definition.

    uv run python tools/export_digitone_cki.py ../CirklonSynthDefs

Pass --check to compare against what is committed, which is what the test
suite does.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from elektron_mcp.digitone.data.sections import (            # noqa: E402
    FX_CHANNEL_SECTIONS, SECTIONS,
)
from rig_midi.cirklon import (                              # noqa: E402
    LABEL_MAX, build_instrument, cki_label, to_cki,
)

# A short tag per section, used only where two sections would otherwise
# show the same label. Three rows all reading MIX, or two reading ATK, are
# legal -- CC_defs is keyed by CC -- but unusable on a track page.
SECTION_TAGS = {
    "amp": "A", "fx": "X", "lfo1": "L1", "lfo2": "L2", "lfo3": "L3",
    "trig": "T", "track": "TR", "misc": "M", "euclid": "E",
    "filter_base_width": "F", "filter_multi_mode": "F",
    "filter_lowpass4": "F", "filter_equalizer": "F",
    "filter_legacy_lp_hp": "F", "filter_comb_minus": "F",
    "filter_comb_plus": "F",
    "send_delay": "D", "send_reverb": "R", "send_chorus": "C",
    "compressor": "K", "master": "MS", "external_in": "I",
}


def disambiguate(sections):
    """Return {section: {ident: spec}} with clashing labels prefixed.

    A label is left alone unless another section in the same definition
    uses it too, so the common case stays exactly as the device shows it.
    """
    seen = {}
    for name, params in sections.items():
        for ident, spec in params.items():
            label = cki_label(f"{name}.{ident}", spec)
            seen.setdefault(label, set()).add(name)
    clashing = {label for label, owners in seen.items() if len(owners) > 1}

    out = {}
    for name, params in sections.items():
        tag = SECTION_TAGS.get(name, name[:2].upper())
        fixed = {}
        for ident, spec in params.items():
            label = cki_label(f"{name}.{ident}", spec)
            if label in clashing:
                room = LABEL_MAX - len(tag) - 1
                spec = dict(spec, cki_label=f"{tag}.{label[:room]}")
            fixed[ident] = spec
        out[name] = fixed
    return out


# Shared by every machine, on the track's own channel.
TRACK_COMMON = ("amp", "fx", "lfo1", "lfo2", "lfo3", "filter_base_width",
                "trig", "track", "misc", "euclid")

MACHINES = {
    "fm_tone": ("DN2 FM Tone", "FMTone"),
    "fm_drum": ("DN2 FM Drum", "FMDrum"),
    "wavetone": ("DN2 Wavetone", "Wavetone"),
    "swarmer": ("DN2 Swarmer", "Swarmer"),
}
FILTERS = {
    "filter_multi_mode": ("Multi", "MultiMode"),
    "filter_lowpass4": ("LP4", "Lowpass4"),
    "filter_equalizer": ("EQ", "Equalizer"),
    "filter_legacy_lp_hp": ("Legacy", "Legacy"),
    "filter_comb_minus": ("Comb-", "CombMinus"),
    "filter_comb_plus": ("Comb+", "CombPlus"),
}
DEFAULT_FILTER = "filter_multi_mode"


def page_one(machine):
    """The machine's SYN page 1, CC 40 to 47, for the track page."""
    params = SECTIONS[machine]
    chosen = [(int(spec["cc_msb"]), f"{machine}.{ident}")
              for ident, spec in params.items()
              if "cc_msb" in spec and 40 <= int(spec["cc_msb"]) <= 47]
    return [name for _, name in sorted(chosen)]


def machine_instrument(machine, filter_machine=DEFAULT_FILTER):
    sections = {machine: SECTIONS[machine],
                filter_machine: SECTIONS[filter_machine]}
    for name in TRACK_COMMON:
        sections[name] = SECTIONS[name]
    slots = page_one(machine)
    return build_instrument(disambiguate(sections), midi_port=1,
                            midi_chan=1, slots=slots, multi=True)


def fx_instrument():
    sections = {name: SECTIONS[name] for name in FX_CHANNEL_SECTIONS}
    # The send effects' own mixes are what you reach for while playing.
    slots = ["send_delay.mix", "send_reverb.mix", "send_chorus.mix",
             "send_delay.time", "send_delay.fdbk", "send_reverb.dec",
             "compressor.mix", "master.over"]
    return build_instrument(disambiguate(sections), midi_port=1,
                            midi_chan=9, slots=slots, no_xpose=True,
                            no_fts=True)


def build_all(every_filter=False):
    files = {}
    for machine, (name, suffix) in MACHINES.items():
        files[f"Digitone2-{suffix}.cki"] = {
            name: machine_instrument(machine),
        }
    if every_filter:
        for filt, (short, fsuffix) in FILTERS.items():
            if filt == DEFAULT_FILTER:
                continue
            group = {}
            for machine, (name, _) in MACHINES.items():
                group[f"{name} {short}"[:16]] = \
                    machine_instrument(machine, filt)
            files[f"Digitone2-Filter{fsuffix}.cki"] = group
    files["Digitone2-SendFX.cki"] = {"DN2 Send FX": fx_instrument()}
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--every-filter", action="store_true",
                    help="also write a file per alternative filter machine")
    args = ap.parse_args()

    problems = []
    for filename, instruments in sorted(
            build_all(args.every_filter).items()):
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
        defs = next(iter(instruments.values()))["CC_defs"]
        print(f"  {filename}: {len(instruments)} instrument(s), "
              f"{len(defs)} CC defs, {len(text)} bytes")

    if args.check:
        for line in problems:
            print(f"  {line}")
        print("up to date" if not problems else f"{len(problems)} stale")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
