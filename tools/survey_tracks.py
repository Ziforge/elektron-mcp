#!/usr/bin/env python3
"""
Find which tracks sound, and which of them reach the slots track 14 cannot.

Two machine parameter slots, CC 60 and 61, exist only on FM TONE and
WAVETONE. Track 14 runs FM DRUM, and the machine cannot be changed over
MIDI -- the Digitone II exposes no CC or NRPN for machine selection. But
another track may already be running one of those machines, and the CC
numbers are the same on every track.

So: play a note on each channel, keep the ones that make a sound, then
probe CC 60 and 61 on those. A track where they move the sound is running
a machine that uses them.
"""

import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mido                                                  # noqa: E402
from rig_audio.analysis import describe, mstft_distance      # noqa: E402

from tools.sweep_device import (                             # noqa: E402
    acquire_lock, capture, release_lock,
)

AUDIBLE_RMS = 0.004


class Bare:
    """A device wrapper that does not assume a parameter map."""

    def __init__(self, port_match, channel=1, note=60, velocity=110,
                 gate_ms=300):
        name = next(p for p in mido.get_output_names()
                    if port_match in p)
        self.port = mido.open_output(name)
        self.channel = channel - 1
        self.note = note
        self.velocity = velocity
        self.gate_ms = gate_ms
        self.retrigger_ms = 0

    def silence(self):
        for control in (123, 120):
            self.port.send(mido.Message(
                "control_change", channel=self.channel, control=control,
                value=0))
        time.sleep(0.04)

    def strike(self):
        self.port.send(mido.Message("note_on", channel=self.channel,
                                    note=self.note, velocity=self.velocity))
        time.sleep(self.gate_ms / 1000.0)
        self.port.send(mido.Message("note_off", channel=self.channel,
                                    note=self.note))

    def cc(self, control, value, channel=None):
        self.port.send(mido.Message(
            "control_change",
            channel=self.channel if channel is None else channel,
            control=control, value=value))
        time.sleep(0.004)

    def close(self):
        for channel in range(16):
            for control in (123, 120):
                self.port.send(mido.Message(
                    "control_change", channel=channel, control=control,
                    value=0))
        self.port.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="Digitone")
    ap.add_argument("--audio-device", default="Elektron Digitone II")
    ap.add_argument("--channels", default="1-16")
    ap.add_argument("--probe-ccs", default="60,61")
    ap.add_argument("--sigma", type=float, default=6.0)
    args = ap.parse_args()

    held = acquire_lock()
    if held is not None:
        print(f"another sweep holds the instrument (pid {held})")
        return 2

    begin, _, end = args.channels.partition("-")
    channels = list(range(int(begin), int(end or begin) + 1))
    probes = [int(c) for c in args.probe_ccs.split(",") if c]

    device = Bare(args.port)
    sounding = []
    try:
        print("which channels make a sound")
        for channel in channels:
            device.channel = channel - 1
            # Open the amp up without assuming anything else about the
            # patch: volume, and an envelope that actually opens.
            for control, value in ((90, 110), (84, 0), (85, 30), (86, 90),
                                   (87, 90), (88, 40)):
                device.cc(control, value)
            time.sleep(0.1)
            audio, sr = capture(device, args.audio_device, 1.0)
            rms = describe(audio, sr).get("rms") or 0.0
            mark = "sounds" if rms > AUDIBLE_RMS else "-"
            print(f"  channel {channel:2d}  rms={rms:.5f}  {mark}")
            if rms > AUDIBLE_RMS:
                sounding.append(channel)

        if not sounding:
            print("\nno channel produced a sound; nothing to probe")
            return 1

        print(f"\nprobing CC {probes} on the {len(sounding)} that sound")
        for channel in sounding:
            device.channel = channel - 1
            for control, value in ((90, 110), (84, 0), (85, 30), (86, 90),
                                   (87, 90), (88, 40)):
                device.cc(control, value)
            time.sleep(0.1)
            ref, sr = capture(device, args.audio_device, 1.0)

            floor = []
            for _ in range(4):
                again, _ = capture(device, args.audio_device, 1.0)
                floor.append(mstft_distance(ref, again, sr)["distance"])
            mean = float(np.mean(floor))
            sd = float(np.std(floor))
            threshold = mean + args.sigma * max(sd, 0.004)

            for control in probes:
                best = 0.0
                for value in (127, 0):
                    device.cc(control, 64)
                    time.sleep(0.02)
                    device.cc(control, value)
                    time.sleep(0.05)
                    probe, _ = capture(device, args.audio_device, 1.0)
                    best = max(
                        best, mstft_distance(ref, probe, sr)["distance"])
                device.cc(control, 64)
                verdict = "RESPONDS" if best > threshold else "-"
                print(f"  channel {channel:2d}  CC {control}  d={best:7.4f} "
                      f"(bar {threshold:.4f})  {verdict}")
    finally:
        device.close()
        release_lock()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
