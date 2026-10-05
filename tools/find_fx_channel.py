#!/usr/bin/env python3
"""
Find the Digitone II's FX CONTROL CH by probing for it.

The send effects, compressor and master overdrive answer on one dedicated
MIDI channel (SETTINGS > MIDI CONFIG > CHANNELS > FX CONTROL CH), and the
device will not tell you which. But it can be found: send a parameter that
exists only on that channel to each channel in turn and see which one
changes the sound.

CC 119, the compressor page's Pattern Volume, is the probe. It is one of
only two FX-channel CCs that no per-track parameter also uses, and being a
level control its effect is unmistakable. The other, CC 12, is the chorus
delay send, which does nothing unless the chorus is already in the path.

A channel set to OFF cannot be found this way, because nothing answers --
the result says so rather than guessing.
"""

import argparse
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mido                                                  # noqa: E402
from rig_audio.analysis import describe, mstft_distance      # noqa: E402

from tools.sweep_device import (                             # noqa: E402
    AMP_PROFILES, Device, baseline_for, capture, sections_for,
)

PROBE_CC = 119
PROBE_LOW = 0
PROBE_REST = 110


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="Digitone")
    ap.add_argument("--audio-device", default="Elektron Digitone II")
    ap.add_argument("--track", type=int, default=14,
                    help="a channel the track actually sounds on")
    ap.add_argument("--machine", default="fm_drum")
    ap.add_argument("--filter", dest="filter_machine",
                    default="filter_multi_mode")
    ap.add_argument("--channels", default="1-16")
    ap.add_argument("--probe-cc", type=int, default=PROBE_CC,
                    help="an FX-channel CC to probe with. 119 is Pattern "
                         "Volume; 92 is the reverb mix, which needs the "
                         "track's reverb send up to be audible")
    ap.add_argument("--probe-low", type=int, default=PROBE_LOW)
    ap.add_argument("--probe-rest", type=int, default=PROBE_REST)
    ap.add_argument("--set", action="append", default=[],
                    metavar="SECTION.PARAM=VALUE",
                    help="override a baseline value, to put the track's "
                         "sound where the probe can act on it")
    ap.add_argument("--repeats", type=int, default=6)
    ap.add_argument("--sigma", type=float, default=5.0)
    args = ap.parse_args()

    begin, _, end = args.channels.partition("-")
    candidates = list(range(int(begin), int(end or begin) + 1))

    sections = sections_for(args.machine, args.filter_machine)
    patch = baseline_for(sections)
    patch["amp"].update(AMP_PROFILES["sustained"])
    patch["amp"]["vol"] = 110
    for name in ("lfo1", "lfo2", "lfo3"):
        patch[name].update({"dep": 0, "dest": 0})
    for assignment in args.set:
        target, _, raw = assignment.partition("=")
        name, _, ident = target.partition(".")
        if name not in patch or ident not in patch[name]:
            print(f"--set names an unknown parameter: {target}")
            return 2
        patch[name][ident] = int(raw)
        print(f"  baseline override: {target} = {int(raw)}")

    device = Device(args.port, args.track, 60, 110, 400)
    port = device.port

    def restore():
        """Put Pattern Volume back up on every channel probed."""
        for channel in candidates:
            port.send(mido.Message("control_change", channel=channel - 1,
                                   control=args.probe_cc,
                                   value=args.probe_rest))
            time.sleep(0.01)

    try:
        print(f"probing with CC {args.probe_cc}: "
              f"{args.probe_rest} -> {args.probe_low}")
        restore()
        device.send_patch(sections, patch)
        ref, sr = capture(device, args.audio_device, 1.4)
        ref_desc = describe(ref, sr)
        if float(ref_desc.get("rms") or 0) < 0.002:
            print("the reference is silent -- check the track sounds on "
                  f"channel {args.track}")
            return 1

        floor = []
        for _ in range(args.repeats):
            device.send_patch(sections, patch)
            again, _ = capture(device, args.audio_device, 1.4)
            floor.append(mstft_distance(ref, again, sr)["distance"])
        mean = statistics.fmean(floor)
        sd = statistics.stdev(floor) if len(floor) > 1 else 0.0
        threshold = mean + args.sigma * sd
        print(f"unchanged {mean:.4f} +/- {sd:.4f} -> a change must exceed "
              f"{threshold:.4f}")

        results = []
        for channel in candidates:
            restore()
            device.send_patch(sections, patch)
            port.send(mido.Message("control_change", channel=channel - 1,
                                   control=args.probe_cc,
                                   value=args.probe_low))
            time.sleep(0.05)
            probe, _ = capture(device, args.audio_device, 1.4)
            d = mstft_distance(ref, probe, sr)["distance"]
            rms = describe(probe, sr).get("rms")
            hit = d > threshold
            results.append((channel, d, rms, hit))
            print(f"  channel {channel:2d}  d={d:7.4f}  rms={rms}"
                  f"  {'<-- responds' if hit else ''}")
    finally:
        restore()
        device.close(sections, patch)

    hits = [c for c, _, _, hit in results if hit]
    print()
    if len(hits) == 1:
        print(f"FX CONTROL CH = {hits[0]}")
    elif not hits:
        print("no channel responded. FX CONTROL CH is most likely OFF; "
              "set it on the device, or the probe's parameter is not "
              "reaching the master bus.")
    else:
        print(f"more than one channel responded ({hits}), so this probe "
              f"did not isolate it. One of them may be a track channel "
              f"whose own CC 119 does something after all.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
