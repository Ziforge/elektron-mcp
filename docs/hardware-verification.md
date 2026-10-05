# Hardware verification

The maps in this repo were transcriptions until they were played. This
records what has been checked against real audio, and how.

`tools/sweep_device.py` sets a parameter, plays a note, records it, and
measures whether the sound moved. `tools/merge_sweeps.py` combines passes.
`tools/check_key_tracking.py` covers the one parameter a single-note sweep
cannot reach.

## Digitone II, track 14, FM DRUM + MULTI-MODE

**81 of 84 parameters verified** across the machine, filter, amp, FX and all
three LFOs.

| section | verified |
|---|---|
| `fm_drum` | 30/30 |
| `fx` | 8/8 |
| `lfo1`, `lfo2`, `lfo3` | 8/8 each |
| `filter_multi_mode` | 7/8 |
| `amp` | 8/9 |
| `filter_base_width` | 4/5 |

Not separated from the noise floor, all three with CC numbers confirmed
against Appendix C of the manual:

- `amp.hold` — moves tonality but under threshold. Its effect overlaps the
  decay stage in a way one captured note cannot separate.
- `filter_multi_mode.rel` — the release stage, after the key is up.
- `filter_base_width.env_reset` — resets the envelope on a *new* trig, so
  by definition it needs two consecutive notes. A one-note probe cannot
  show it.

## Three map bugs this found

- **LFO 3 had invented CC numbers** (121–128). The manual lists no CC for
  LFO 3 at all, only NRPN. CC 123 is All Notes Off, so setting LFO 3 FADE
  silenced the track; 124–127 switch the device's MIDI mode; 128 is not a
  valid CC, which is what made the sweep crash on its first run.
- **The NRPN MSB and LSB were sent reversed**, so LFO 3 had never worked by
  any route.
- **The LFO destination range was declared 25–50** while its own option
  table ran 0–99, leaving most destinations unselectable and a mid-range
  value on no destination at all.

## Method notes, each earned

- **Resend the whole patch before every probe.** Restoring only the last
  parameter lets damage accumulate.
- **Only one SYN machine and one filter machine at a time.** They share
  CC 40–47 by design. A first attempt swept all sixteen sections and had 29
  of 30 FM DRUM parameters overwritten before the note sounded; every probe
  measured the same patch and the numbers looked fine.
- **Wait for silence before each capture.** Otherwise each recording holds
  a different amount of the previous note still ringing, which alone put
  the unchanged-patch distance at 0.28 against a real-change bar of 0.15.
- **Align on the onset.** The distance compares frame by frame and is not
  shift invariant.
- **Measure the noise floor every run, and refuse an unusable one.** A
  nearly closed filter or near-silent envelope gives an unstable log-STFT;
  one configuration measured 2.31 against itself.
- **Report descriptors, not just a distance.** A scalar says something
  changed, not what. Level, brightness, bandwidth, noisiness, decay,
  tonality and stereo position say whether a parameter did what its name
  implies. A mono-summed distance cannot see panning at all; `amp.pan`
  verifies only through the stereo measure.
- **A parameter is only audible if what it feeds is on.** A bipolar depth
  at raw 64 is zero depth, and an LFO with no destination cannot make its
  own speed or waveform heard. Thirty parameters first read as inaudible
  for that reason alone.
- **A parameter verified in any pass is verified.** The baseline that
  reveals one can mask another: turning an LFO's depth up to expose its
  waveform leaves the depth itself near its limit.

## Not yet verified

The Analog Heat, Analog Rytm MKII and Octatrack MKII maps are tested
transcriptions with no hardware check — none was connected. The sweep runs
against any of them once they are.

Also unverified: the Digitone's other machines. Switching machine needs a
hand on the device, since the Digitone II exposes no CC or NRPN for machine
selection.
