#!/usr/bin/env python3
"""
Verify sequencer parameters by counting trigs, not by comparing spectra.

The euclidean generators decide how many steps fire in a bar and where.
That is a question about onsets, and onsets can be counted exactly. A
spectral comparison is the wrong instrument for it: it answers "does this
bar sound different", which parameter locks and a free-running voice can
answer yes to on their own -- which is why the bar-to-bar floor never fell
below about 0.5 and every trig parameter read as inconclusive.

Counting trigs is immune to all of that. A p-lock changes how a hit sounds,
not whether it happens, and a voice with random phase still starts when it
is told to.

The mutes are the sharpest case: a muted track fires nothing, so its onset
count goes to zero. Nothing subtle to argue about.
"""

import argparse
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mido                                                  # noqa: E402
from rig_audio.analysis import describe, onset_count         # noqa: E402
from rig_audio.capture import SubprocessRecorder             # noqa: E402

from elektron_mcp.digitone.data.sections import SECTIONS     # noqa: E402

from tools.sweep_device import (                             # noqa: E402
    acquire_lock, cc_of, nrpn_of, release_lock,
)

# Section, identifier, and the values to try. Chosen so the prediction is
# about trig count: a pulse generator at zero should fire nothing, at a high
# value should fire often.
TARGETS = (
    ("euclid", "pl1", (0, 8, 16)),
    ("euclid", "pl2", (0, 8, 16)),
    ("euclid", "euc", (0, 1)),
    ("euclid", "ro1", (0, 8)),
    ("euclid", "ro2", (0, 8)),
    ("euclid", "tro", (0, 8)),
    ("euclid", "bool", (0, 1, 2)),
    ("track", "mute", (0, 1, 127)),
    ("misc", "pat_mute", (0, 1, 127)),
    ("trig", "len", (1, 64, 127)),
    ("trig", "vel", (1, 64, 127)),
    ("trig", "note", (24, 60, 96)),
)


class Clock:
    def __init__(self, port, bpm):
        import threading
        self.port = port
        self.interval = 60.0 / (bpm * 24)
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        nxt = time.perf_counter()
        while not self._stopping.is_set():
            nxt += self.interval
            delay = nxt - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            try:
                self.port.send(mido.Message("clock"))
            except Exception:
                return

    def start(self):
        self._thread.start()

    def stop(self):
        self._stopping.set()
        self._thread.join(timeout=1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="Digitone")
    ap.add_argument("--audio-device", default="Elektron Digitone II")
    ap.add_argument("--track", type=int, default=14)
    ap.add_argument("--bpm", type=float, default=120.0)
    ap.add_argument("--bars", type=float, default=2.0)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--hold", action="append", default=[],
                    metavar="SECTION.PARAM=VALUE",
                    help="held for every count. The euclidean generators "
                         "do nothing unless euclid mode is on, so probing "
                         "them without holding euclid.euc=1 measures "
                         "nothing")
    ap.add_argument("--only", default="",
                    help="comma-separated section.param to probe")
    args = ap.parse_args()

    held = acquire_lock()
    if held is not None:
        print(f"another sweep holds the instrument (pid {held})")
        return 2

    seconds = args.bars * 4 * 60.0 / args.bpm
    port = mido.open_output(next(p for p in mido.get_output_names()
                                 if args.port in p))
    channel = args.track - 1
    clock = Clock(port, args.bpm)

    def send(spec, value):
        cc = cc_of(spec)
        if cc is not None:
            port.send(mido.Message("control_change", channel=channel,
                                   control=cc, value=int(value)))
            time.sleep(0.01)
            return
        msb, lsb = nrpn_of(spec)
        for control, data in ((99, msb), (98, lsb), (6, int(value)),
                              (38, 0)):
            port.send(mido.Message("control_change", channel=channel,
                                   control=control, value=int(data)))
            time.sleep(0.005)

    def count():
        """Trigs in a fixed number of bars, from the top of the pattern."""
        port.send(mido.Message("stop"))
        for control in (123, 120):
            port.send(mido.Message("control_change", channel=channel,
                                   control=control, value=0))
        time.sleep(0.25)
        rec = SubprocessRecorder(seconds=seconds + 0.4,
                                 device=args.audio_device).start()
        port.send(mido.Message("start"))
        audio, sr = rec.finish()
        port.send(mido.Message("stop"))
        mono = audio.mean(axis=1) if audio.ndim > 1 else audio
        return onset_count(mono, sr), (describe(audio, sr).get("rms") or 0.0)

    held_values = []
    for item in args.hold:
        target, _, value = item.partition("=")
        section, _, ident = target.partition(".")
        spec = SECTIONS.get(section, {}).get(ident)
        if spec is None:
            print(f"--hold names an unknown parameter: {target}")
            return 2
        held_values.append((spec, int(value), target))

    wanted = {t for t in args.only.split(",") if t}

    try:
        clock.start()
        for spec, value, target in held_values:
            send(spec, value)
            print(f"  holding {target} = {value}")
        time.sleep(0.2)
        print(f"{args.bars:.0f} bars at {args.bpm:.0f} BPM "
              f"({seconds:.1f}s per capture)\n")

        base = [count() for _ in range(args.repeats)]
        counts = [n for n, _ in base]
        level = statistics.fmean(r for _, r in base)
        spread = max(counts) - min(counts)
        print(f"unchanged pattern: {counts} trigs, rms {level:.4f}")
        if level < 0.004:
            print("the pattern is silent; nothing to count")
            return 1
        print(f"  count varies by {spread} between identical passes\n")

        for section, ident, values in TARGETS:
            if wanted and f"{section}.{ident}" not in wanted:
                continue
            spec = SECTIONS.get(section, {}).get(ident)
            if spec is None:
                continue
            seen = []
            for value in values:
                # Re-apply the holds: the full set is not resent between
                # counts, so anything the probe disturbed must come back.
                for hspec, hvalue, _ in held_values:
                    send(hspec, hvalue)
                send(spec, value)
                time.sleep(0.2)
                n, rms = count()
                seen.append((value, n, rms))
            send(spec, 64 if ident not in ("euc",) else 0)
            shown = "  ".join(f"{v}:{n}" for v, n, _ in seen)
            got = [n for _, n, _ in seen]
            moved = max(got) - min(got)
            bar = max(3 * spread, 4)
            verdict = "RESPONDS" if moved > bar else "INCONCLUSIVE"
            print(f"  {section}.{ident:<10} {shown:<30} "
                  f"range {moved:<3} (bar {bar}) {verdict}")
    finally:
        clock.stop()
        port.send(mido.Message("stop"))
        for control in (123, 120):
            port.send(mido.Message("control_change", channel=channel,
                                   control=control, value=0))
        port.close()
        release_lock()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
