#!/usr/bin/env python3
"""
Verify a parameter map against real hardware by ear, not by assertion.

For each parameter: play a note and record it, change that one parameter,
play the same note again, and measure whether the sound actually moved. A
parameter whose CC is wrong produces no change.

Three things this does deliberately, each because not doing them produced a
wrong answer earlier in this project:

- The complete patch is resent before every probe. Restoring only the one
  parameter that was last changed lets damage accumulate, so that every
  later reading measures the wreckage of the earlier ones rather than the
  parameter under test.
- The noise floor is measured, not assumed. Two recordings of an unchanged
  patch still differ; until you know by how much, you cannot tell a real
  change from jitter. An earlier round of this work selected between
  differences of 0.3 while the measurement spread was 0.83.
- Each capture waits for the previous note to decay first, and is aligned
  on its own onset before comparing. Without the wait, every recording
  catches a different amount of the last note still ringing, and that
  alone put the unchanged-patch distance at 0.28 -- three times the bar a
  real change had to clear. With it, the floor is 0.085.
- No audible change is reported as INCONCLUSIVE, never as a failure. A
  parameter can be genuinely inert in a given patch -- a delay send with
  the delay off, a filter envelope depth with a flat envelope -- and that
  says nothing about whether its CC is right.

Two measures are taken, because one is blind to the other's parameters. A
multi-resolution log-STFT distance catches anything that changes the
spectrum, but it sums to mono first, so a pan control moves nothing it can
see; a stereo balance reading catches those. Each is compared against its
own measured floor.

Only one SYN machine and one filter machine can be swept at a time, and
the set is refused if any CC is claimed twice. This is not a convenience:
the Digitone II's machines deliberately share CC 40 to 47, so sending every
section in turn leaves the last one written standing. An earlier run of
this swept all sixteen sections at once and had 29 of the 30 FM DRUM
parameters overwritten before the note sounded, which made every probe
measure the same patch. It read as plausible numbers and was worthless.

Alongside the distance, each parameter's descriptors are reported -- level,
brightness, decay, noisiness, stereo position -- so the result says what
moved and not merely that something did. A parameter whose name implies
pitch had better change the spectrum, not the level.

Elektron devices do not echo incoming CC, so audio is the only evidence
available. This cannot check a parameter's *name*, only that its CC
reaches something that changes the sound in a particular way.
"""

import argparse
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mido                                                  # noqa: E402
import numpy as np                                           # noqa: E402
from rig_audio.analysis import mstft_distance                # noqa: E402
from rig_audio.capture import (                              # noqa: E402
    SubprocessRecorder, record,
)

from rig_audio.analysis import describe                      # noqa: E402
from elektron_mcp.digitone.data.sections import SECTIONS     # noqa: E402

# One per track. Each names the same CCs as its siblings, so only one can
# be in a sweep at a time.
SYN_MACHINES = ("fm_drum", "fm_tone", "swarmer", "wavetone")
FILTER_MACHINES = ("filter_multi_mode", "filter_lowpass4",
                   "filter_equalizer", "filter_legacy_lp_hp",
                   "filter_comb_minus", "filter_comb_plus")
# Shared by every machine, so always included.
COMMON = ("amp", "fx", "lfo1", "lfo2", "lfo3", "filter_base_width")

# What each descriptor change means, for reporting what actually moved.
DESCRIPTORS = {
    "rms": ("level", 0.15),
    "spectral_centroid_hz": ("brightness", 0.08),
    "rolloff_95_hz": ("bandwidth", 0.08),
    "spectral_flatness": ("noisiness", 0.12),
    "decay_t20_ms": ("decay", 0.15),
    "harmonic_ratio": ("tonality", 0.10),
}

BASELINE_VALUE = 64
# A patch the probes start from. Everything else sits at mid. The amplitude
# envelope is loud but short: loud so a change anywhere is audible, short so
# the tail clears before the next probe rather than bleeding into it.
# A parameter can only be heard if whatever it feeds is switched on. Most
# of these exist because the first full sweep left 30 parameters
# INCONCLUSIVE purely for want of that: a bipolar depth sitting at raw 64
# is zero depth, and an LFO with no valid destination cannot make its own
# speed or waveform audible.
# Two amplitude profiles. A short percussive note keeps the tail clear
# between probes, but it ends before any later envelope stage or LFO cycle
# can be heard -- which is why the filter's decay, sustain and release, and
# every LFO parameter but depth, first read as inaudible. The sustained
# profile holds the note open so time-varying parameters have something to
# vary.
AMP_PROFILES = {
    "percussive": {"atk": 0, "hold": 20, "dec": 60, "sus": 0, "rel": 20,
                   "vol": 110, "pan": 64},
    "sustained": {"atk": 0, "hold": 80, "dec": 110, "sus": 110, "rel": 50,
                  "vol": 110, "pan": 64},
}

BASELINE_OVERRIDES = {
    "amp": dict(AMP_PROFILES["percussive"]),
    "filter_multi_mode": {
        "freq": 70, "reso": 50, "type": 0,
        # Bipolar -64..64, so raw 64 is no depth at all and the four
        # envelope stages below it do nothing.
        "env_depth": 127,
        "atk": 10, "dec": 60, "sus": 40, "rel": 40,
    },
    "filter_base_width": {"base": 40, "wdth": 90, "env_delay": 0,
                          "env_reset": 0, "key_tracking": 0},
    # dest 67 is FILTER: Freq. Each LFO needs a real destination and some
    # depth before its speed, waveform or phase can be heard. Trig mode
    # with start phase 0 keeps it deterministic per note -- free-running
    # would make every capture differ and swamp the noise floor.
    "lfo1": {"dest": 67, "dep": 100, "spd": 90, "mult": 2, "wave": 1,
             "mode": 1, "sph": 0, "fade": 64},
    "lfo2": {"dest": 67, "dep": 100, "spd": 90, "mult": 2, "wave": 1,
             "mode": 1, "sph": 0, "fade": 64},
    "lfo3": {"dest": 67, "dep": 100, "spd": 90, "mult": 2, "wave": 1,
             "mode": 1, "sph": 0, "fade": 64},
}
SILENCE_PEAK = 0.004
SILENCE_TRIES = 14
# An unchanged patch should measure close to itself. Much above this and
# the baseline is not stable enough to measure anything against -- a
# near-closed filter or a near-silent envelope gives an unstable log-STFT,
# and every verdict taken against it is noise. Seen in practice at 2.31.
FLOOR_UNUSABLE = 0.5
QUIET_RMS = 0.002


def cc_of(spec):
    return int(spec["cc_msb"]) if "cc_msb" in spec else None


def nrpn_of(spec):
    """(MSB, LSB) for a parameter, or None.

    The data files name these fields inversely to their meaning: nrpn_lsb
    holds the bank the manual calls the MSB.
    """
    if "nrpn_msb" not in spec or "nrpn_lsb" not in spec:
        return None
    return int(spec["nrpn_lsb"]), int(spec["nrpn_msb"])


def sections_for(machine, filter_machine):
    """The sections that can be swept together without a CC collision."""
    chosen = [machine, filter_machine] + list(COMMON)
    sections = {name: SECTIONS[name] for name in chosen}
    claims = {}
    clashes = []
    for name, params in sections.items():
        for ident, spec in params.items():
            cc = cc_of(spec)
            if cc is None:
                continue
            if cc in claims:
                clashes.append(f"CC {cc}: {claims[cc]} and {name}.{ident}")
            claims[cc] = f"{name}.{ident}"
    if clashes:
        raise ValueError("chosen sections collide: " + "; ".join(clashes))
    return sections


def changed_descriptors(ref_desc, probe_desc):
    """Which descriptors moved, and by how much, as fractions."""
    moved = {}
    for key, (label, tolerance) in DESCRIPTORS.items():
        a, b = ref_desc.get(key), probe_desc.get(key)
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            continue
        scale = max(abs(a), abs(b), 1e-9)
        delta = abs(b - a) / scale
        if delta > tolerance:
            moved[label] = round(delta, 3)
    return moved


def baseline_for(sections):
    """{section: {ident: value}} -- the patch every probe returns to."""
    patch = {}
    for name, params in sections.items():
        over = BASELINE_OVERRIDES.get(name, {})
        patch[name] = {i: over.get(i, BASELINE_VALUE) for i in params}
    return patch


def probe_values(spec):
    """Values to try, furthest first. Both ends, because a parameter can be
    inert at one of them and alive at the other."""
    lo = spec.get("min_midi", 0)
    hi = spec.get("max_midi", 127)
    return [v for v in (hi, lo) if v != BASELINE_VALUE]


class Device:
    def __init__(self, port_match, channel, note, velocity, gate_ms):
        self.port = mido.open_output(
            next(p for p in mido.get_output_names() if port_match in p))
        self.channel = channel - 1
        self.note = note
        self.velocity = velocity
        self.gate_ms = gate_ms

    def send_patch(self, sections, patch, skip=None):
        for name, params in sections.items():
            for ident, spec in params.items():
                if skip == (name, ident):
                    continue
                self.send_param(spec, patch[name][ident])
                # ~1 kB/s across a full-map resend: fast enough that the
                # sweep finishes, slow enough not to flood the input.
                time.sleep(0.003)
        # Elektron's MIDI input needs a moment to settle after a burst this
        # size before the next note reflects all of it.
        time.sleep(0.12)

    def send_param(self, spec, value):
        """Set one parameter, by CC or by NRPN as the map declares."""
        cc = cc_of(spec)
        if cc is not None:
            self.port.send(mido.Message(
                "control_change", channel=self.channel, control=cc,
                value=int(value)))
            time.sleep(0.003)
            return True
        pair = nrpn_of(spec)
        if pair is None:
            return False
        # CC 99/98 select the parameter, 6/38 carry the 14-bit value.
        msb, lsb = pair
        for control, data in ((99, msb), (98, lsb),
                              (6, int(value)), (38, 0)):
            self.port.send(mido.Message(
                "control_change", channel=self.channel, control=control,
                value=int(data)))
            time.sleep(0.003)
        return True

    def strike(self):
        self.port.send(mido.Message("note_on", channel=self.channel,
                                    note=self.note, velocity=self.velocity))
        time.sleep(self.gate_ms / 1000.0)
        self.port.send(mido.Message("note_off", channel=self.channel,
                                    note=self.note))

    def close(self, sections=None, patch=None):
        """Leave the track as it was found, not on the last probe value.

        An earlier run of this ended with the amplitude volume still at the
        probe's zero, which left the track silent and looked like a broken
        audio path.
        """
        self.port.send(mido.Message("control_change", channel=self.channel,
                                    control=123, value=0))
        if sections and patch:
            self.send_patch(sections, patch)
        self.port.close()


def wait_for_silence(audio_device):
    """Let the previous note decay, so a capture holds one note only."""
    for _ in range(SILENCE_TRIES):
        audio, _ = record(seconds=0.12, device=audio_device)
        if float(np.abs(audio).max()) < SILENCE_PEAK:
            return True
    return False


def balance(audio):
    """Where the sound sits between the channels, 0.5 being centred."""
    if audio.ndim < 2 or audio.shape[1] < 2:
        return 0.5
    left = float(np.abs(audio[:, 0]).mean())
    right = float(np.abs(audio[:, 1]).mean())
    total = left + right
    return 0.5 if total <= 0 else left / total


def align(audio, samplerate, keep=0.7, frac=0.05):
    """Trim to the note's own onset.

    mstft_distance compares frame by frame, so it is not shift invariant:
    a note landing a few milliseconds later reads as a different sound.
    """
    mono = np.abs(audio).max(axis=1) if audio.ndim > 1 else np.abs(audio)
    peak = mono.max()
    if peak <= 0:
        return audio
    start = int(np.argmax(mono > frac * peak))
    want = int(keep * samplerate)
    segment = audio[start:start + want]
    if len(segment) < want:
        pad = [(0, want - len(segment))] + [(0, 0)] * (audio.ndim - 1)
        segment = np.pad(segment, pad)
    return segment


def capture(device, audio_device, seconds):
    wait_for_silence(audio_device)
    rec = SubprocessRecorder(seconds=seconds, device=audio_device).start()
    device.strike()
    audio, samplerate = rec.finish()
    return align(audio, samplerate), samplerate


def measure_noise_floor(device, sections, patch, audio_device, seconds,
                        repeats):
    """How much two recordings of the same patch differ, on both measures."""
    device.send_patch(sections, patch)
    ref, sr = capture(device, audio_device, seconds)
    distances, balances = [], []
    for _ in range(repeats):
        device.send_patch(sections, patch)
        again, _ = capture(device, audio_device, seconds)
        distances.append(mstft_distance(ref, again, sr)["distance"])
        balances.append(abs(balance(again) - balance(ref)))
    return ref, sr, distances, balances


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="Digitone")
    ap.add_argument("--audio-device", default="Elektron Digitone II")
    ap.add_argument("--track", type=int, default=14,
                    help="MIDI channel the track is on")
    ap.add_argument("--machine", default="fm_drum",
                    choices=SYN_MACHINES,
                    help="the SYN machine assigned to the track")
    ap.add_argument("--filter", dest="filter_machine",
                    default="filter_multi_mode", choices=FILTER_MACHINES,
                    help="the filter machine assigned to the track")
    ap.add_argument("--sections", default="",
                    help="restrict to these, from the compatible set")
    ap.add_argument("--set", action="append", default=[],
                    metavar="SECTION.PARAM=VALUE",
                    help="override one baseline value. A parameter is only "
                         "audible if what it feeds is switched on, so this "
                         "is how a straggler gets the conditions it needs")
    ap.add_argument("--quiet-lfos", action="store_true",
                    help="zero the LFO depths in the baseline. Three LFOs "
                         "modulating a long note make each capture less "
                         "repeatable, which raises the noise floor and "
                         "hides small changes elsewhere")
    ap.add_argument("--params", default="",
                    help="comma-separated section.param to probe; the rest "
                         "of the patch is still sent, just not probed")
    ap.add_argument("--profile", default="percussive",
                    choices=sorted(AMP_PROFILES),
                    help="percussive keeps probes quick; sustained holds "
                         "the note open so envelope stages and LFO cycles "
                         "are audible")
    ap.add_argument("--note", type=int, default=60)
    ap.add_argument("--velocity", type=int, default=100)
    ap.add_argument("--gate-ms", type=int, default=400)
    ap.add_argument("--seconds", type=float, default=1.2)
    ap.add_argument("--noise-repeats", type=int, default=8)
    ap.add_argument("--sigma", type=float, default=5.0,
                    help="how many noise deviations counts as a change")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    try:
        compatible = sections_for(args.machine, args.filter_machine)
    except ValueError as e:
        print(e)
        return 2
    wanted = [s for s in args.sections.split(",") if s] or list(compatible)
    missing = [s for s in wanted if s not in compatible]
    if missing:
        print(f"not sweepable alongside {args.machine} and "
              f"{args.filter_machine}: {missing}")
        print(f"available: {sorted(compatible)}")
        return 2
    sections = {s: compatible[s] for s in wanted}

    # A targeted re-probe still sends the whole patch -- the point of the
    # full resend is that the parameter under test is the only thing that
    # differs -- but only probes what was asked for.
    only = {p for p in args.params.split(",") if p}
    unknown = [p for p in only
               if p.split(".", 1)[0] not in sections
               or p.split(".", 1)[-1] not in sections[p.split(".", 1)[0]]]
    if unknown:
        print(f"unknown parameters: {unknown}")
        return 2

    BASELINE_OVERRIDES["amp"] = dict(AMP_PROFILES[args.profile])
    if args.quiet_lfos:
        for name in ("lfo1", "lfo2", "lfo3"):
            BASELINE_OVERRIDES[name] = {**BASELINE_OVERRIDES[name],
                                        "dep": 0, "dest": 0}
    if args.profile == "sustained" and args.gate_ms < 700:
        # No point holding the envelope open and then releasing the key
        # before it gets there.
        args.gate_ms = 700
        args.seconds = max(args.seconds, 1.6)
    patch = baseline_for(sections)
    for assignment in args.set:
        target, _, raw = assignment.partition("=")
        name, _, ident = target.partition(".")
        if name not in patch or ident not in patch[name]:
            print(f"--set names an unknown parameter: {target}")
            return 2
        patch[name][ident] = int(raw)
        print(f"  baseline override: {target} = {int(raw)}")
    probing = [(name, ident) for name, params in sections.items()
               for ident in params
               if not only or f"{name}.{ident}" in only]
    total = len(probing)

    device = Device(args.port, args.track, args.note, args.velocity,
                    args.gate_ms)
    print(f"track {args.track}, machine {args.machine}, filter "
          f"{args.filter_machine}, {args.profile} "
          f"(gate {args.gate_ms} ms)")
    print(f"{len(sections)} sections, {total} parameters")
    try:
        print("measuring the noise floor...")
        ref, sr, floor, bal_floor = measure_noise_floor(
            device, sections, patch, args.audio_device, args.seconds,
            args.noise_repeats)
        if max(abs(ref).max(), 0) < 1e-4:
            print("  the capture is silent -- check the track is audible "
                  "and the audio input is the device")
            return 1
        mean = statistics.fmean(floor)
        sd = statistics.stdev(floor) if len(floor) > 1 else 0.0
        threshold = mean + args.sigma * sd
        bal_mean = statistics.fmean(bal_floor)
        bal_sd = statistics.stdev(bal_floor) if len(bal_floor) > 1 else 0.0
        bal_threshold = max(bal_mean + args.sigma * bal_sd, 0.004)
        print(f"  unchanged-patch distance {mean:.4f} +/- {sd:.4f}"
              f"  -> a change must exceed {threshold:.4f}")
        print(f"  unchanged-patch balance  {bal_mean:.4f} +/- {bal_sd:.4f}"
              f"  -> a shift must exceed {bal_threshold:.4f}")
        ref_balance = balance(ref)
        ref_desc = describe(ref, sr)
        if mean > FLOOR_UNUSABLE:
            print(f"  the baseline is not stable enough to measure: an "
                  f"unchanged patch differs by {mean:.3f}. Pick settings "
                  f"where the note is clearly audible -- a nearly closed "
                  f"filter or a near-silent envelope does this.")
            return 1
        if float(ref_desc.get("rms") or 0) < QUIET_RMS:
            print(f"  the baseline is too quiet to measure: rms "
                  f"{ref_desc.get('rms')}. Raise the level or lengthen "
                  f"the envelope.")
            return 1
        print(f"  baseline: rms {ref_desc.get('rms')}, centroid "
              f"{ref_desc.get('spectral_centroid_hz')} Hz, decay "
              f"{ref_desc.get('decay_t20_ms')} ms, flatness "
              f"{ref_desc.get('spectral_flatness')}")

        results, done = [], 0
        for name, ident in probing:
            spec = sections[name][ident]
            done += 1
            cc = cc_of(spec)
            pair = nrpn_of(spec)
            if cc is None and pair is None:
                results.append({"section": name, "param": ident,
                                "verdict": "UNADDRESSABLE"})
                continue
            how_sent = "CC" if cc is not None else "NRPN"
            address = cc if cc is not None else f"{pair[0]}:{pair[1]}"
            best, best_value, best_bal = 0.0, None, 0.0
            best_moved = {}
            for value in probe_values(spec):
                device.send_patch(sections, patch, skip=(name, ident))
                device.send_param(spec, value)
                time.sleep(0.05)
                probe, _ = capture(device, args.audio_device,
                                   args.seconds)
                d = mstft_distance(ref, probe, sr)["distance"]
                shift = abs(balance(probe) - ref_balance)
                moved = changed_descriptors(ref_desc,
                                            describe(probe, sr))
                if d > best:
                    best, best_value, best_moved = d, value, moved
                best_bal = max(best_bal, shift)
            spectral = best > threshold
            stereo = best_bal > bal_threshold
            verdict = "RESPONDS" if spectral or stereo else "INCONCLUSIVE"
            how = "spectrum" if spectral else ("stereo" if stereo
                                               else "")
            if stereo and "position" not in best_moved:
                best_moved["position"] = round(best_bal, 3)
            results.append({
                "section": name, "param": ident,
                "addressed_by": how_sent, "address": address,
                "distance": round(best, 4),
                "balance_shift": round(best_bal, 4),
                "at_value": best_value, "verdict": verdict,
                "evidence": how, "changed": best_moved,
            })
            moved_text = ", ".join(sorted(best_moved)) or "-"
            print(f"  [{done:3d}/{total}] {name}.{ident:<18} "
                  f"{how_sent:<4} {str(address):>5}  d={best:7.4f}  "
                  f"{verdict:<12} {moved_text}")
    finally:
        device.close(sections, patch)

    kinds = {}
    for r in results:
        for label in r.get("changed", {}):
            kinds[label] = kinds.get(label, 0) + 1
    responds = [r for r in results if r["verdict"] == "RESPONDS"]
    incon = [r for r in results if r["verdict"] == "INCONCLUSIVE"]
    print(f"\n{len(responds)}/{total} responded, {len(incon)} inconclusive")
    for name in sections:
        got = [r for r in responds if r["section"] == name]
        print(f"  {name:22s} {len(got):3d}/{len(sections[name])}")
    if kinds:
        print("\nwhat moved, across all parameters:")
        for label, count in sorted(kinds.items(), key=lambda kv: -kv[1]):
            print(f"  {label:12s} {count}")

    report = {
        "track": args.track, "note": args.note,
        "machine": args.machine, "filter": args.filter_machine,
        "baseline_descriptors": ref_desc,
        "noise_floor": {"mean": mean, "sd": sd, "threshold": threshold,
                        "samples": floor,
                        "balance_mean": bal_mean, "balance_sd": bal_sd,
                        "balance_threshold": bal_threshold},
        "settings": {"seconds": args.seconds, "sigma": args.sigma,
                     "gate_ms": args.gate_ms, "profile": args.profile},
        "results": results,
    }
    if args.out:
        with open(args.out, "w") as handle:
            json.dump(report, handle, indent=1)
        print(f"report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
