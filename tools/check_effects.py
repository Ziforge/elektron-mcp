#!/usr/bin/env python3
"""
Check that the send effects do what their names say, not merely something.

The sweep answers a weak question: did the sound change when this CC moved?
A wrong CC that happens to land on another live parameter answers yes, and
one did -- CC 79 read as an external input's delay send while actually
driving the track's sample rate reduction.

Each effect has a signature that can be checked instead:

- A delay repeats the signal at an interval. Autocorrelation of the tail
  shows a peak at that lag, and raising DELAY TIME should move the peak in
  proportion. Rank correlation between the setting and the measured lag is
  the test.
- A reverb lengthens the decay. The measured T20 should rise monotonically
  with DECAY TIME.
- Feedback should raise how many repeats are detectable.

These can fail. A map with the right CC and a mislabelled meaning passes
the sweep and fails here, which is the point.
"""

import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.sweep_device import (                             # noqa: E402
    AMP_PROFILES, Device, acquire_lock, baseline_for, capture,
    release_lock, sections_for,
)


def mono(audio):
    return audio.mean(axis=1) if audio.ndim > 1 else audio


def echo_lag_ms(audio, samplerate, lo_ms=20.0, hi_ms=None):
    """Where the strongest repeat sits, by autocorrelation of the envelope.

    The envelope rather than the waveform, because a delay repeats the
    whole event and its phase is not preserved.
    """
    x = np.abs(mono(audio))
    if x.max() <= 0:
        return None
    # Smooth to an envelope at ~1 kHz, then remove the mean so the
    # correlation measures repetition and not overall level.
    step = max(1, samplerate // 1000)
    env = x[: len(x) // step * step].reshape(-1, step).mean(axis=1)
    env = env - env.mean()
    if not np.any(env):
        return None
    corr = np.correlate(env, env, mode="full")[len(env) - 1:]
    # Search as far as the recording allows. A fixed 900 ms ceiling made
    # the two longest delay settings -- which sit past a second -- read as
    # no echo at all and pulled the correlation negative, when the device
    # was tracking its setting perfectly at about 11 ms per unit.
    if hi_ms is None:
        hi_ms = len(corr) * 0.9
    lo, hi = int(lo_ms), min(int(hi_ms), len(corr) - 1)
    if hi <= lo:
        return None
    window = corr[lo:hi]
    peak = float(np.max(window))
    # argmax always returns an index, so without a significance test a
    # single hit with no repeat at all reports a confident echo.
    if corr[0] <= 0 or peak / corr[0] < 0.12:
        return None
    lag = float(lo + int(np.argmax(window)))
    # A peak sitting on the edge of the search window is the envelope's own
    # short-term self-similarity, not a repeat. Reporting it as a
    # measurement broke the ranking: one such reading took an otherwise
    # perfectly linear delay response to a rank correlation of zero.
    if lag <= lo_ms + 3:
        return None
    return lag


def late_energy(audio, samplerate, start_ms=350.0, end_ms=2200.0):
    """Energy well after the note, relative to the note itself.

    This is what a reverb decay control changes. T20 cannot see it: it
    measures a 20 dB fall from the peak, which the dry hit reaches long
    before any tail matters, so T20 read the same 55 ms at every decay
    setting and said nothing about the reverb at all.
    """
    x = np.abs(mono(audio))
    if x.max() <= 0:
        return 0.0
    begin = int(start_ms / 1000 * samplerate)
    finish = min(int(end_ms / 1000 * samplerate), len(x))
    if finish <= begin:
        return 0.0
    head = x[:begin]
    reference = float(np.sqrt(np.mean(head ** 2))) if len(head) else 0.0
    tail = float(np.sqrt(np.mean(x[begin:finish] ** 2)))
    return tail / reference if reference > 0 else 0.0


def repeat_count(audio, samplerate, floor_db=-30.0):
    """How many distinct bursts are audible after the first."""
    x = np.abs(mono(audio))
    if x.max() <= 0:
        return 0
    step = max(1, samplerate // 1000)
    env = x[: len(x) // step * step].reshape(-1, step).mean(axis=1)
    threshold = env.max() * (10 ** (floor_db / 20))
    above = env > threshold
    # Count rising edges, one per burst, counting a burst that is already
    # underway at the first sample -- otherwise every count is one short.
    edges = int(np.sum(above[1:] & ~above[:-1]))
    return edges + (1 if above[0] else 0)


def spearman(a, b):
    """Rank correlation, so a proportional-but-not-linear response passes.

    Tied values must share a rank. Giving them distinct ranks made a
    constant series correlate perfectly with anything, so a parameter that
    changed nothing would have passed as working -- which would defeat the
    purpose of the check.
    """
    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while (j + 1 < len(order)
                   and values[order[j + 1]] == values[order[i]]):
                j += 1
            shared = (i + j) / 2.0
            for k in range(i, j + 1):
                out[order[k]] = shared
            i = j + 1
        return out

    ra, rb = ranks(a), ranks(b)
    n = len(a)
    if n < 3:
        return 0.0
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = sum((r - ma) ** 2 for r in ra) ** 0.5
    db = sum((r - mb) ** 2 for r in rb) ** 0.5
    return 0.0 if da == 0 or db == 0 else num / (da * db)


def spread(values):
    """How far the measurement actually moved, as a fraction of its size.

    Rank correlation says the response is ordered, not that it exists. Four
    reverb tails measuring 55 ms apart from noise in the decimals ranked at
    rho +0.949 and passed, which is a flat response dressed as a working
    one. The measurement has to move as well as rank.
    """
    if not values:
        return 0.0
    lo, hi = min(values), max(values)
    scale = max(abs(hi), abs(lo), 1e-9)
    return (hi - lo) / scale


def run(device, sections, patch, audio_device, section, ident, values,
        seconds, measure):
    """Set a parameter to each value and measure the result."""
    spec = sections[section][ident]
    out = []
    for value in values:
        device.send_patch(sections, patch, skip=(section, ident))
        device.set_in(section, spec, value)
        time.sleep(0.08)
        # Keep nearly the whole recording: an effect's whole point is
        # what happens after the note, and the default trim throws that
        # away.
        audio, sr = capture(device, audio_device, seconds,
                            keep=seconds - 0.2)
        out.append((value, measure(audio, sr)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="Digitone")
    ap.add_argument("--audio-device", default="Elektron Digitone II")
    ap.add_argument("--track", type=int, default=14)
    ap.add_argument("--fx-channel", type=int, required=True)
    ap.add_argument("--machine", default="fm_drum")
    ap.add_argument("--filter", dest="filter_machine",
                    default="filter_multi_mode")
    ap.add_argument("--seconds", type=float, default=2.6)
    args = ap.parse_args()

    held = acquire_lock()
    if held is not None:
        print(f"another sweep holds the instrument (pid {held})")
        return 2

    sections = sections_for(args.machine, args.filter_machine,
                            args.fx_channel)
    patch = baseline_for(sections)
    # A short, bright hit so a repeat is a distinct event rather than a
    # smear, and the sends fully open so the effects are in the path.
    patch["amp"].update(AMP_PROFILES["percussive"])
    patch["amp"].update({"dec": 30, "sus": 0, "rel": 10, "vol": 110})
    for name in ("lfo1", "lfo2", "lfo3"):
        patch[name].update({"dep": 0, "dest": 0})
    patch["fx"].update({"del_": 120, "rev": 0, "chr": 0})
    patch["send_delay"].update({"mix": 120, "fdbk": 60, "ping": 0,
                                "hpf": 0, "lpf": 127, "rev": 0})
    patch["send_reverb"].update({"mix": 0})
    patch["compressor"]["pat_vol"] = 110

    device = Device(args.port, args.track, 60, 110, 60, 0, args.fx_channel)
    failures = []
    try:
        print("DELAY TIME -> measured echo spacing")
        values = [20, 45, 70, 95, 120]
        rows = run(device, sections, patch, args.audio_device,
                   "send_delay", "time", values, args.seconds, echo_lag_ms)
        for value, lag in rows:
            print(f"  TIME {value:3d} -> echo at {lag} ms"
                  if lag else f"  TIME {value:3d} -> no repeat found")
        got = [(v, lag) for v, lag in rows if lag]
        if len(got) < 3:
            failures.append("delay time: too few measurable repeats")
        else:
            lags = [lag for _, lag in got]
            rho = spearman([v for v, _ in got], lags)
            moved = spread(lags)
            print(f"  rank correlation setting vs measured lag: {rho:+.3f}"
                  f", spacing spread {moved:.0%}")
            if moved < 0.25:
                failures.append(
                    f"delay time: the measured spacing barely moves across "
                    f"the range ({moved:.0%}), so nothing is tracking "
                    f"anything")
            elif rho < 0.8:
                failures.append(
                    f"delay time: the measured spacing does not track the "
                    f"setting (rho {rho:+.3f})")

        print("\nDELAY FEEDBACK -> number of repeats")
        rows = run(device, sections, patch, args.audio_device,
                   "send_delay", "fdbk", [0, 40, 80, 115], args.seconds,
                   repeat_count)
        for value, n in rows:
            print(f"  FDBK {value:3d} -> {n} bursts")
        counts = [n for _, n in rows]
        # Repeat counting saturates: once the tail is dense, more feedback
        # does not add countable bursts, so strict ranking is the wrong
        # expectation. What a feedback control must do is turn a couple of
        # repeats into many.
        none_set, most_set = counts[0], max(counts[1:])
        print(f"  with none: {none_set} bursts; at most: {most_set}")
        if most_set < none_set + 3:
            failures.append(
                f"delay feedback: {none_set} bursts with none and only "
                f"{most_set} at the top, which is not a feedback control "
                f"working")

        print("\nREVERB DECAY -> measured T20")
        patch["fx"].update({"del_": 0, "rev": 120})
        patch["send_delay"]["mix"] = 0
        patch["send_reverb"].update({"mix": 120, "pre": 0, "hpf": 0,
                                     "lpf": 127})
        rows = run(device, sections, patch, args.audio_device,
                   "send_reverb", "dec", [10, 45, 80, 120], args.seconds,
                   late_energy)
        for value, tail in rows:
            print(f"  DEC {value:3d} -> late energy {tail:.4f}")
        got = [(v, t) for v, t in rows if t is not None]
        if len(got) < 3:
            failures.append("reverb decay: too few measurable tails")
        else:
            tails = [t for _, t in got]
            rho = spearman([v for v, _ in got], tails)
            moved = spread(tails)
            print(f"  rank correlation: {rho:+.3f}, late-energy spread "
                  f"{moved:.0%}")
            if moved < 0.25:
                failures.append(
                    f"reverb decay: the tail length barely moves across "
                    f"the range ({moved:.0%}); ranking alone would have "
                    f"passed this")
            elif rho < 0.8:
                failures.append(
                    f"reverb decay: the tail does not lengthen with it "
                    f"(rho {rho:+.3f})")
    finally:
        device.close(sections, patch)
        release_lock()

    print()
    if failures:
        for line in failures:
            print(f"FAIL  {line}")
        return 1
    print("all three effects behave as their names say")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
