#!/usr/bin/env python3
"""
Verify filter key tracking, which no single-note sweep can.

Key tracking makes the filter cutoff follow the note played. At one pitch
it does nothing by definition, so the sweep reports it inconclusive and is
right to. The test is a difference of differences: play a low note and a
high note with tracking off, then the same two with tracking on, and the
gap between the two notes' brightness should widen.

Known limit: this needs a tonal machine. On FM DRUM the broadband
transient dominates the spectral centroid whatever the filter is doing, so
the gap stays within noise and the test reports INCONCLUSIVE even though
the sweep hears the parameter clearly. Run it on a track set to FM TONE or
WAVETONE. The machine cannot be changed over MIDI -- the Digitone II
exposes no CC or NRPN for machine selection, only the eight knob slots per
page -- so that is a setting to make on the device first.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rig_audio.analysis import describe                      # noqa: E402

from tools.sweep_device import (                             # noqa: E402
    AMP_PROFILES, Device, capture, sections_for, baseline_for,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="Digitone")
    ap.add_argument("--audio-device", default="Elektron Digitone II")
    ap.add_argument("--track", type=int, default=14)
    ap.add_argument("--machine", default="fm_drum")
    ap.add_argument("--filter", dest="filter_machine",
                    default="filter_multi_mode")
    ap.add_argument("--low", type=int, default=36)
    ap.add_argument("--high", type=int, default=84)
    args = ap.parse_args()

    sections = sections_for(args.machine, args.filter_machine)
    patch = baseline_for(sections)
    patch["amp"].update(AMP_PROFILES["sustained"])
    # The filter has to be the thing shaping the sound, or the machine's
    # own spectrum swamps a cutoff shift. Partly closed with resonance up
    # does that; fully closed would make the capture near-silent and
    # unmeasurable. No envelope, so pitch is the only thing moving it.
    patch["filter_multi_mode"].update({"freq": 40, "reso": 95,
                                       "env_depth": 64, "type": 0})
    patch["fm_drum"].update({"lev": 110, "dec": 110, "nlev": 20})

    device = Device(args.port, args.track, args.low, 110, 700)
    spec = sections["filter_base_width"]["key_tracking"]
    try:
        readings = {}
        for tracking in (0, 127):
            for note in (args.low, args.high):
                device.send_patch(sections, patch)
                device.send_param(spec, tracking)
                time.sleep(0.05)
                device.note = note
                audio, sr = capture(device, args.audio_device, 1.6)
                readings[(tracking, note)] = describe(audio, sr)
    finally:
        device.note = args.low
        device.close(sections, patch)

    print(f"{'tracking':>9} {'note':>5} {'centroid Hz':>12} "
          f"{'rolloff Hz':>11}")
    for (tracking, note), d in readings.items():
        print(f"{tracking:>9} {note:>5} {d['spectral_centroid_hz']:>12.0f} "
              f"{d['rolloff_95_hz']:>11.0f}")

    def gap(tracking):
        lo = readings[(tracking, args.low)]["spectral_centroid_hz"]
        hi = readings[(tracking, args.high)]["spectral_centroid_hz"]
        return hi - lo

    off, on = gap(0), gap(127)
    print("\ncentroid gap between the two notes:")
    print(f"  tracking off: {off:>9.0f} Hz")
    print(f"  tracking on : {on:>9.0f} Hz")
    widened = abs(on) > abs(off) * 1.25
    print(f"\n{'RESPONDS' if widened else 'INCONCLUSIVE'}: the gap "
          f"{'widened' if widened else 'did not widen'} with tracking on")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
