#!/usr/bin/env python3
"""
Settle individual addresses the broad sweeps could not.

The sweep probes a whole section under one set of conditions. The addresses
it leaves open usually need particular conditions instead: a compressor
needs a signal hot enough to make it engage, CC 60 and 61 exist only on a
machine track 14 is not running, and an envelope reset acts on a second
trig or not at all.

So this takes an explicit list of addresses, a channel, and whatever
overrides those addresses need, and measures only them -- with as many
repeats as it takes to get a floor worth comparing against.

Addresses are given as CC numbers, or as msb:lsb for NRPN.
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
    acquire_lock, balance, capture, descriptor_deltas, release_lock,
)

# Enough of a voice to measure, without assuming which machine is loaded:
# these CCs mean the same thing on every machine.
GENERIC_STABILISE = (
    (90, 110),   # amp volume
    (84, 0),     # amp attack
    (85, 20),    # amp hold
    (86, 55),    # amp decay
    (87, 0),     # amp sustain
    (88, 15),    # amp release
    (89, 64),    # amp pan centred
    (109, 0),    # LFO 1 depth off
    (118, 0),    # LFO 2 depth off
    (105, 0),    # LFO 1 destination none
    (114, 0),    # LFO 2 destination none
    (29, 0),     # chorus send off
    (30, 0),     # delay send off
    (31, 0),     # reverb send off
    # CC 62 and 63 are deliberately not touched. They are machine
    # dependent -- oscillator reset on FM DRUM, noise type and character on
    # WAVETONE -- so setting them blindly stabilises one machine and
    # destabilises another. Setting them raised track 1's floor from 0.045
    # to 0.21 by switching its noise on.
)
# LFO 3 has no CC at all, so zeroing it needs NRPN. Leaving it running is
# enough on its own to make a voice unrepeatable: track 1 measured a floor
# of 6.84 against itself with LFO 1 and 2 silenced but LFO 3 untouched.
GENERIC_STABILISE_NRPN = (
    (1, 72, 0),   # LFO 3 depth
    (1, 61, 0),   # LFO 3 destination
)


class Plain:
    def __init__(self, port_match, channel, note, velocity, gate_ms,
                 retrigger_ms=0):
        name = next(p for p in mido.get_output_names() if port_match in p)
        self.port = mido.open_output(name)
        self.channel = channel - 1
        self.note = note
        self.velocity = velocity
        self.gate_ms = gate_ms
        self.retrigger_ms = retrigger_ms

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
        if self.retrigger_ms:
            time.sleep(self.retrigger_ms / 1000.0)
            self.port.send(mido.Message(
                "note_on", channel=self.channel, note=self.note,
                velocity=self.velocity))
            time.sleep(self.gate_ms / 1000.0)
            self.port.send(mido.Message("note_off", channel=self.channel,
                                        note=self.note))

    def cc(self, control, value):
        self.port.send(mido.Message("control_change", channel=self.channel,
                                    control=int(control),
                                    value=int(value)))
        time.sleep(0.004)

    def nrpn(self, msb, lsb, value):
        for control, data in ((99, msb), (98, lsb), (6, int(value)),
                              (38, 0)):
            self.cc(control, data)

    def close(self):
        self.silence()
        self.port.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="Digitone")
    ap.add_argument("--audio-device", default="Elektron Digitone II")
    ap.add_argument("--channel", type=int, required=True,
                    help="the channel the addresses are probed on")
    ap.add_argument("--note-channel", type=int, default=0,
                    help="play the note on this channel instead. Needed "
                         "for the FX control channel, where the parameters "
                         "live but no voice does: the compressor can only "
                         "be measured while a track is sounding")
    ap.add_argument("--note-set", action="append", default=[],
                    metavar="CC=VALUE",
                    help="held on the note channel, to put the voice where "
                         "the addresses under test can act on it")
    ap.add_argument("--addresses", required=True,
                    help="comma-separated CC numbers, or msb:lsb for NRPN")
    ap.add_argument("--set", action="append", default=[],
                    metavar="CC=VALUE",
                    help="held for every measurement, to give the "
                         "addresses under test something to act on")
    ap.add_argument("--no-stabilise", action="store_true")
    ap.add_argument("--note", type=int, default=60)
    ap.add_argument("--velocity", type=int, default=110)
    ap.add_argument("--gate-ms", type=int, default=250)
    ap.add_argument("--retrigger-ms", type=int, default=0)
    ap.add_argument("--seconds", type=float, default=1.4)
    ap.add_argument("--keep", type=float, default=1.1)
    ap.add_argument("--repeats", type=int, default=12)
    ap.add_argument("--sigma", type=float, default=5.0)
    args = ap.parse_args()

    held = acquire_lock()
    if held is not None:
        print(f"another sweep holds the instrument (pid {held})")
        return 2

    targets = []
    for token in args.addresses.split(","):
        token = token.strip()
        if not token:
            continue
        if ":" in token:
            msb, _, lsb = token.partition(":")
            targets.append(("nrpn", int(msb), int(lsb)))
        else:
            targets.append(("cc", int(token), None))

    holds = []
    for item in args.set:
        control, _, value = item.partition("=")
        holds.append((int(control), int(value)))

    voice_channel = args.note_channel or args.channel
    device = Plain(args.port, voice_channel, args.note, args.velocity,
                   args.gate_ms, args.retrigger_ms)
    probe_channel = args.channel - 1

    note_holds = []
    for item in args.note_set:
        control, _, value = item.partition("=")
        note_holds.append((int(control), int(value)))

    def on_probe_channel(control, value):
        device.port.send(mido.Message(
            "control_change", channel=probe_channel, control=int(control),
            value=int(value)))
        time.sleep(0.004)

    def prepare():
        # The stabiliser belongs on the channel that makes the sound.
        if not args.no_stabilise:
            for control, value in GENERIC_STABILISE:
                device.cc(control, value)
            for msb, lsb, value in GENERIC_STABILISE_NRPN:
                device.nrpn(msb, lsb, value)
        for control, value in note_holds:
            device.cc(control, value)
        # The holds for the addresses under test belong on their own.
        for control, value in holds:
            on_probe_channel(control, value)
        time.sleep(0.12)

    def grab():
        return capture(device, args.audio_device, args.seconds,
                       keep=args.keep)

    try:
        prepare()
        ref, sr = grab()
        ref_desc = describe(ref, sr)
        print(f"probing channel {args.channel}, note on channel "
              f"{voice_channel}: reference rms {ref_desc.get('rms')}")
        if (ref_desc.get("rms") or 0) < 0.002:
            print("  too quiet to measure anything against")
            return 1

        dists, wander, bals = [], {}, []
        for _ in range(args.repeats):
            prepare()
            again, _ = grab()
            dists.append(mstft_distance(ref, again, sr)["distance"])
            bals.append(abs(balance(again) - balance(ref)))
            for label, delta in descriptor_deltas(
                    ref_desc, describe(again, sr)).items():
                wander.setdefault(label, []).append(delta)
        mean = statistics.fmean(dists)
        sd = statistics.stdev(dists) if len(dists) > 1 else 0.0
        bar = mean + args.sigma * sd
        floors = {}
        for label, samples in wander.items():
            m = statistics.fmean(samples)
            s = statistics.stdev(samples) if len(samples) > 1 else 0.0
            floors[label] = max(m + args.sigma * s, 0.05)
        bal_bar = max(statistics.fmean(bals) + args.sigma * (
            statistics.stdev(bals) if len(bals) > 1 else 0.0), 0.004)
        print(f"  floor {mean:.4f} +/- {sd:.4f} -> bar {bar:.4f}")
        print("  descriptor floors: " + ", ".join(
            f"{k} {v:.3f}" for k, v in sorted(floors.items())))
        print()

        for kind, a, b in targets:
            label = f"CC {a}" if kind == "cc" else f"NRPN {a}:{b}"
            best, moved, best_bal = 0.0, {}, 0.0
            for value in (127, 0):
                prepare()
                if kind == "cc":
                    on_probe_channel(a, value)
                else:
                    for control, data in ((99, a), (98, b),
                                          (6, value), (38, 0)):
                        on_probe_channel(control, data)
                time.sleep(0.06)
                probe, _ = grab()
                best = max(best,
                           mstft_distance(ref, probe, sr)["distance"])
                best_bal = max(best_bal,
                               abs(balance(probe) - balance(ref)))
                for name, delta in descriptor_deltas(
                        ref_desc, describe(probe, sr)).items():
                    if delta > floors.get(name, float("inf")):
                        moved[name] = max(moved.get(name, 0.0), delta)
            verdict = ("RESPONDS"
                       if best > bar or moved or best_bal > bal_bar
                       else "INCONCLUSIVE")
            detail = ", ".join(sorted(moved)) or "-"
            print(f"  {label:14s} d={best:7.4f}  {verdict:<12} {detail}")
    finally:
        device.close()
        release_lock()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
