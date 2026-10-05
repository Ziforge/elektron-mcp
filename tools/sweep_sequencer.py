#!/usr/bin/env python3
"""
Reach the parameters a played note cannot.

Fifteen parameters govern what the device's own sequencer plays rather than
how a voice sounds: the trig note, velocity and length, the seven euclidean
controls, the track and pattern mutes. An incoming MIDI note bypasses all
of them, so no amount of audio probing with a played note can say whether
their CC numbers are right.

Running the device's sequencer instead puts them in the signal path. The
Digitone follows MIDI transport, so sending Start and a clock makes its
pattern play, and then muting a track or changing a euclidean pulse count
changes what is heard.

This first checks that the sequencer actually responds, because if the
device is not set to follow external transport nothing here means anything
-- and silence would otherwise read as "every parameter is dead".
"""

import argparse
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mido                                                  # noqa: E402
from rig_audio.analysis import describe, mstft_distance      # noqa: E402

from elektron_mcp.digitone.data.sections import SECTIONS     # noqa: E402

from tools.sweep_device import (                             # noqa: E402
    acquire_lock, cc_of, nrpn_of, release_lock,
)
from rig_audio.capture import SubprocessRecorder             # noqa: E402

SEQUENCER_SECTIONS = ("trig", "track", "euclid", "misc")


class Clock(threading.Thread):
    """A MIDI clock, so the device's sequencer has something to follow."""

    def __init__(self, port, bpm=120.0):
        super().__init__(daemon=True)
        self.port = port
        self.interval = 60.0 / (bpm * 24)
        self._stop = threading.Event()

    def run(self):
        nxt = time.perf_counter()
        while not self._stop.is_set():
            nxt += self.interval
            delay = nxt - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            try:
                self.port.send(mido.Message("clock"))
            except Exception:
                return

    def stop(self):
        self._stop.set()
        self.join(timeout=1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="Digitone")
    ap.add_argument("--audio-device", default="Elektron Digitone II")
    ap.add_argument("--track", type=int, default=14)
    ap.add_argument("--bpm", type=float, default=120.0)
    ap.add_argument("--seconds", type=float, default=4.0)
    ap.add_argument("--repeats", type=int, default=6)
    ap.add_argument("--sigma", type=float, default=5.0)
    args = ap.parse_args()

    held = acquire_lock()
    if held is not None:
        print(f"another sweep holds the instrument (pid {held})")
        return 2

    name = next(p for p in mido.get_output_names() if args.port in p)
    port = mido.open_output(name)
    channel = args.track - 1
    clock = Clock(port, args.bpm)

    def capture_bars():
        rec = SubprocessRecorder(seconds=args.seconds,
                                 device=args.audio_device).start()
        time.sleep(args.seconds * 0.9)
        return rec.finish()

    def set_param(spec, value):
        cc = cc_of(spec)
        if cc is not None:
            port.send(mido.Message("control_change", channel=channel,
                                   control=cc, value=int(value)))
            time.sleep(0.01)
            return
        pair = nrpn_of(spec)
        msb, lsb = pair
        for control, data in ((99, msb), (98, lsb), (6, int(value)),
                              (38, 0)):
            port.send(mido.Message("control_change", channel=channel,
                                   control=control, value=int(data)))
            time.sleep(0.004)

    try:
        print(f"starting the sequencer at {args.bpm:.0f} BPM")
        clock.start()
        port.send(mido.Message("start"))
        time.sleep(1.0)

        playing, sr = capture_bars()
        level = describe(playing, sr).get("rms") or 0.0
        print(f"  pattern level: rms {level:.5f}")
        if level < 0.004:
            print("\nthe sequencer is not producing audio. Either the "
                  "pattern is empty on this track, or the device is not "
                  "following external transport\n"
                  "  (SETTINGS > MIDI CONFIG > SYNC > TRANSPORT RECEIVE "
                  "and CLOCK RECEIVE both need to be on).\n"
                  "Without it every parameter here would read as dead, "
                  "which would be the tool's fault and not the map's.")
            return 1

        floor = []
        for _ in range(args.repeats):
            again, _ = capture_bars()
            floor.append(mstft_distance(playing, again, sr)["distance"])
        mean = sum(floor) / len(floor)
        sd = (sum((d - mean) ** 2 for d in floor) / len(floor)) ** 0.5
        threshold = mean + args.sigma * max(sd, 0.01)
        print(f"  bar-to-bar variation {mean:.4f} +/- {sd:.4f} -> a change "
              f"must exceed {threshold:.4f}")
        print("  (a sequencer repeats, so two passes of the same pattern "
              "should measure close)\n")

        results = []
        for section in SEQUENCER_SECTIONS:
            for ident, spec in SECTIONS[section].items():
                cc = cc_of(spec)
                pair = nrpn_of(spec)
                address = f"CC {cc}" if cc is not None \
                    else f"NRPN {pair[0]}:{pair[1]}"
                baseline = 64 if cc is not None else 64
                best = 0.0
                for value in (spec.get("max_midi", 127),
                              spec.get("min_midi", 0)):
                    set_param(spec, value)
                    time.sleep(0.2)
                    probe, _ = capture_bars()
                    best = max(best, mstft_distance(
                        playing, probe, sr)["distance"])
                set_param(spec, baseline)
                verdict = "RESPONDS" if best > threshold else "INCONCLUSIVE"
                results.append((section, ident, verdict))
                print(f"  {section}.{ident:<12} {address:<14} "
                      f"d={best:7.4f}  {verdict}")
    finally:
        clock.stop()
        port.send(mido.Message("stop"))
        for control in (123, 120):
            port.send(mido.Message("control_change", channel=channel,
                                   control=control, value=0))
        port.close()
        release_lock()

    got = sum(1 for _, _, v in results if v == "RESPONDS")
    print(f"\n{got}/{len(results)} sequencer parameters responded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
