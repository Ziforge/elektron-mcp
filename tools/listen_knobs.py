#!/usr/bin/env python3
"""
Verify the map against the device's own opinion, by listening.

The Digitone's DATA ENTRY knobs transmit the CC of whatever parameter they
are editing. That is ground truth: turn the FEEDBACK knob on the DELAY page
and the device says which CC it means, with no audio analysis and no
inference. Where the sweep can only report that a sound changed, this says
what the device thinks the control is.

Which is the stronger evidence. A sweep verdict rests on a measurement
being sound -- and one of those measurements read an external input's delay
send as responding when the probe was really driving the track's sample
rate reduction. This cannot make that mistake.

Four settings on the device gate it, under SETTINGS > MIDI CONFIG:

  PORT CONFIG > OUTPUT TO      = USB (or MIDI+USB)
  PORT CONFIG > PARAM OUTPUT   = CC
  PORT CONFIG > ENCODER DEST   = INT + EXT     <- the real gate
  PORT CONFIG > OUTPUT CH      = TRACK or AUTO

ENCODER DEST is the one usually missed: on INT the knobs change the sound
and send nothing at all.

Channel matters to the reading. A CC arriving on a track's channel means a
track parameter; the same number on the FX control channel means a send
effect or mixer parameter. CC 70 is a machine parameter on one and the
chorus high-pass on the other.
"""

import argparse
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mido                                                  # noqa: E402

from elektron_mcp.digitone.data.sections import (            # noqa: E402
    FX_CHANNEL_SECTIONS, SECTIONS,
)


def candidates(cc, role):
    """Map entries that claim this CC, for this kind of channel."""
    found = []
    for name, params in SECTIONS.items():
        is_fx = name in FX_CHANNEL_SECTIONS
        if (role == "fx") != is_fx:
            continue
        for ident, spec in params.items():
            if "cc_msb" in spec and int(spec["cc_msb"]) == cc:
                found.append(f"{name}.{ident}")
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="Digitone")
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--track", type=int, default=14)
    ap.add_argument("--fx-channel", type=int, default=0)
    args = ap.parse_args()

    name = next((p for p in mido.get_input_names() if args.port in p), None)
    if name is None:
        print(f"no MIDI input matching {args.port!r}")
        return 1

    print(f"listening on {name} for {args.seconds:.0f}s -- turn the knobs "
          f"you want identified")
    print("(nothing arriving at all means ENCODER DEST is still INT)\n")

    seen = Counter()
    nrpn = Counter()
    pending = {}
    other = Counter()
    with mido.open_input(name) as port:
        deadline = time.time() + args.seconds
        while time.time() < deadline:
            for message in port.iter_pending():
                if message.type != "control_change":
                    other[message.type] += 1
                    continue
                channel = message.channel + 1
                # CC 99/98 then 6/38 is an NRPN, not four parameters.
                if message.control in (99, 98, 6, 38):
                    pending.setdefault(channel, {})[message.control] = \
                        message.value
                    held = pending[channel]
                    if 99 in held and 98 in held and 6 in held:
                        nrpn[(channel, held[99], held[98])] += 1
                        pending[channel] = {}
                    continue
                seen[(channel, message.control)] += 1
            time.sleep(0.01)

    if not seen and not nrpn:
        print("nothing arrived.")
        print("  - ENCODER DEST must be INT + EXT, not INT")
        print("  - OUTPUT TO must include USB")
        print("  - PARAM OUTPUT selects CC or NRPN; both are read here")
        if other:
            print(f"  (non-CC messages did arrive: {dict(other)}, so the "
                  f"port itself is fine)")
        return 1

    print(f"{'channel':>8} {'CC':>5} {'count':>6}  map says")
    for (channel, cc), count in sorted(seen.items()):
        if args.fx_channel and channel == args.fx_channel:
            role = "fx"
        else:
            role = "track"
        names = candidates(cc, role)
        if names:
            verdict = ", ".join(names)
        else:
            # Try the other role before calling it unknown.
            alt = candidates(cc, "fx" if role == "track" else "track")
            verdict = (f"NOT IN MAP for a {role} channel"
                       + (f" (but is {', '.join(alt)} on the other)"
                          if alt else ""))
        print(f"{channel:>8} {cc:>5} {count:>6}  {verdict}")

    for (channel, msb, lsb), count in sorted(nrpn.items()):
        print(f"{channel:>8} NRPN {msb}:{lsb} {count:>4}  "
              f"(PARAM OUTPUT is set to NRPN)")

    unknown = [k for k in seen
               if not candidates(k[1], "fx" if args.fx_channel
                                 and k[0] == args.fx_channel else "track")]
    print()
    print(f"{len(seen)} distinct CCs seen, {len(unknown)} not in the map "
          f"for the channel they arrived on")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
