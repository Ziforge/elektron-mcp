#!/usr/bin/env python3
"""
Work out whether a channel is really the FX control channel, or the auto
channel wearing its clothes.

The Digitone's AUTO CHANNEL routes whatever arrives on it to the currently
active track. If the FX control channel and the auto channel are set to the
same number -- or if what was found was only ever the auto channel -- then a
CC sent there lands on the active track instead of on the send effects, and
any verdict about an FX parameter whose CC number a track parameter also
uses is measuring the wrong thing.

This settles it by comparison. Send the same CC to the candidate channel and
to the track's own channel and describe both results. If the two move the
sound the same way, the candidate is reaching the track, not the FX block.

CC 79 is the discriminator by default: on a track it is sample rate
reduction, which moves brightness and noisiness unmistakably, and on the FX
block it is the right input's delay send, which with nothing plugged in
should do nothing at all.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mido                                                  # noqa: E402
from rig_audio.analysis import describe, mstft_distance      # noqa: E402

from tools.sweep_device import (                             # noqa: E402
    AMP_PROFILES, Device, baseline_for, capture,
    descriptor_deltas, sections_for,
)

WATCH = ("level", "brightness", "bandwidth", "noisiness", "tonality")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="Digitone")
    ap.add_argument("--audio-device", default="Elektron Digitone II")
    ap.add_argument("--track", type=int, default=14)
    ap.add_argument("--candidate", type=int, default=9,
                    help="the channel under suspicion")
    ap.add_argument("--cc", type=int, default=79)
    ap.add_argument("--value", type=int, default=120)
    ap.add_argument("--machine", default="fm_drum")
    ap.add_argument("--filter", dest="filter_machine",
                    default="filter_multi_mode")
    args = ap.parse_args()

    sections = sections_for(args.machine, args.filter_machine)
    patch = baseline_for(sections)
    patch["amp"].update(AMP_PROFILES["sustained"])
    patch["amp"]["vol"] = 110
    for name in ("lfo1", "lfo2", "lfo3"):
        patch[name].update({"dep": 0, "dest": 0})

    device = Device(args.port, args.track, 60, 110, 400)
    try:
        device.send_patch(sections, patch)
        ref, sr = capture(device, args.audio_device, 1.6)
        ref_desc = describe(ref, sr)

        shots = {}
        for label, channel in (("track", args.track),
                               ("candidate", args.candidate)):
            device.send_patch(sections, patch)
            device.port.send(mido.Message(
                "control_change", channel=channel - 1, control=args.cc,
                value=args.value))
            time.sleep(0.06)
            audio, _ = capture(device, args.audio_device, 1.6)
            shots[label] = (mstft_distance(ref, audio, sr)["distance"],
                            descriptor_deltas(ref_desc, describe(audio, sr)))
    finally:
        device.close(sections, patch)

    print(f"CC {args.cc} = {args.value}, against the same patch\n")
    print(f"{'':12s} {'distance':>9}  " +
          "  ".join(f"{w:>10}" for w in WATCH))
    for label, (d, deltas) in shots.items():
        row = "  ".join(f"{deltas.get(w, 0.0):10.3f}" for w in WATCH)
        name = f"ch {args.track}" if label == "track" \
            else f"ch {args.candidate}"
        print(f"{name:12s} {d:9.4f}  {row}")

    d_track, dev_track = shots["track"]
    d_cand, dev_cand = shots["candidate"]
    agree = sum(
        1 for w in WATCH
        if abs(dev_track.get(w, 0.0) - dev_cand.get(w, 0.0)) < 0.1
        and max(dev_track.get(w, 0.0), dev_cand.get(w, 0.0)) > 0.1
    )
    print()
    if d_cand < 0.1 and d_track > 0.2:
        print(f"channel {args.candidate} is NOT reaching the track: the CC "
              f"did nothing there and plenty on the track's own channel. "
              f"An FX verdict on this CC is trustworthy.")
    elif agree >= 2:
        print(f"channel {args.candidate} IS reaching the track: both move "
              f"the sound the same way on {agree} descriptors. It is acting "
              f"as the auto channel, so any FX verdict on a CC that a track "
              f"parameter also uses is measuring the track.")
    else:
        print("inconclusive: the two differ but not in a way that says "
              "which. Try another CC whose track meaning has an obvious "
              "signature.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
