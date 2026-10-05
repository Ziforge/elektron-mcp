# Hardware verification

The maps in this repo were transcriptions until they were played. This
records what has been checked against real audio, and how.

`tools/sweep_device.py` sets a parameter, plays a note, records it, and
measures whether the sound moved. `tools/merge_sweeps.py` combines passes.
`tools/check_key_tracking.py` covers the one parameter a single-note sweep
cannot reach.

## Digitone II: 118 of 146 distinct addresses verified

Counted by address rather than by parameter, because the machines share
their CC numbers: an unverified machine parameter is usually an address
already verified under another name. By parameter the figure is 112 of 244,
which understates it for that reason.

| section | verified |
|---|---|
| `fm_drum` | 30/30 |
| `amp` | 9/9 |
| `fx` | 8/8 |
| `lfo1`, `lfo2`, `lfo3` | 8/8 each |
| `filter_multi_mode` | 8/8 |
| `send_delay` | 8/8 |
| `send_reverb` | 7/7 |
| `send_chorus` | 7/7 |
| `master` | 1/1 |
| `filter_base_width` | 4/5 |
| `compressor` | 9/9 |
| `trig` | 1/7 |
| `track` | 1/2 |

Reproduce with:

    uv run python tools/merge_sweeps.py <reports> --by-address

### What is left, and why

Only three of the 34 are open questions. The rest are unreachable by audio
for structural reasons, not for want of effort:

- **`external_in`, 11 addresses.** They control the external audio inputs
  and nothing is plugged in. Correctly silent; this is the map being right,
  not unverified.
- **`trig` 6 and `euclid` 7.** Sequencer-domain: they govern what a
  pattern plays, and an incoming MIDI note bypasses them. Two methods were
  tried and both exhausted. Driving the device's own sequencer works -- it
  follows MIDI transport -- but a spectral comparison of one bar against
  the next cannot settle them: the floor will not fall below about 0.5,
  because a p-locked pattern and a random-phase voice both make one bar
  genuinely differ from the next.

  Counting trigs instead is the right question for the euclidean
  generators, since their whole job is deciding how many steps fire, and
  counting is immune to p-locks: a lock changes how a hit sounds, not
  whether it happens. With euclid mode held on, none of them moved the
  count beyond its noise -- ranges of 1 to 6 against a spread of 4. So the
  euclidean parameters are not reaching the device at all.

  All seven are NRPN bank 3, and bank 3 has never been shown to work.
  Bank 1 has: LFO 3 responds on 1:72. The one bank-3 parameter that is
  audible in principle is portamento, CC 9 and 65 with NRPN 3:6 and 3:7,
  which glides pitch between two different notes -- but it reads 0.29 to
  0.34 against a 0.54 bar on FM DRUM, where portamento may simply do
  nothing. Bank 3 therefore remains unproven rather than disproven, and it
  is the single most valuable thing left to settle: if the bank and
  parameter numbers are the wrong way round for bank 3 as they were for
  the fields generally, that is a real defect across 13 addresses.
- **The two mutes, CC 94 and CC 110.** Confirmed non-functional over MIDI
  by two independent methods. Spectrally, muting every track leaves the
  level unchanged; by trig count, a muted track still fires 27, 24 and 28
  trigs where a working mute would fire none. Neither CC nor NRPN 1:108
  has any effect. Both numbers are from Appendix C, so the map matches the
  manual and the manual is not reproducible here.
- **CC 61.** On WAVETONE this is noise WDTH, and track 1 -- the only track
  reaching these slots -- runs WAVETONE. Measuring the width of a noise
  source against the noise it makes does not separate from its own floor:
  0.22 against a bar of 0.35 with the noise up. CC 60 verified at 0.14.
- **`filter_base_width.env_reset`.** Acts on a new trig by definition, so
  it needs two notes in succession.

## What the CC numbers already cover

The machine and filter parameters are knob slots, not fixed controls.
Appendix C.3 names them "Data entry knob A-H (machine dependent)" and C.4
does the same for two of the filter slots: the CC numbers are identical
whichever machine a track runs, and only the meaning changes.

That matters for what counts as verified. `swarmer` and all six filter
machines use CCs already covered by `fm_drum` and `filter_multi_mode`;
`fm_tone` and `wavetone` reach exactly two slots the others do not, CC 60
and 61. So hardware-verifying one machine verified the CC *numbers* for all
four machines and all six filters, and the unverified CC surface is two
numbers rather than the 183 parameters a naive count suggests.

What stays unverified is the per-machine naming, which audio cannot
establish in principle -- a knob slot responds identically whatever it is
called. That comes from Appendix A, or from the device's own knobs.

## Choosing the metric matters more than tightening it

Three results came from changing what was measured rather than measuring
better:

- The send effects read 1/8, 0/7 and 4/7 under a sustained note trimmed at
  700 ms, and 8/8, 7/7 and 7/7 under a 60 ms hit with three seconds of tail
  kept. Nothing about the map changed.
- The delay could not be verified by "did the sound change" at all, and is
  verified exactly by echo spacing: 232, 507, 783 and 1059 ms across
  settings 20 to 95, which is 11.03 ms per unit.
- The reverb's decay is invisible to T20, which measures the dry hit, and
  obvious in late energy: 0.0035 to 0.1449, rank correlation +1.000.

And one result came from a metric that could not work in principle: a
mono-summed spectral distance cannot see a pan control, so `amp.pan`
verifies only through stereo balance, at 0.43.

## Two facts about the instrument this turned up

**The compressor only compresses with the sidechain source at 0.** With it
at 127 the threshold, attack, release and ratio all read as doing nothing,
because the compressor never engages -- so there is nothing for them to act
on. With the source at 0 every one of them responds immediately: threshold
0.30, ratio 0.63, attack 0.31, release 0.49. Five addresses that looked
dead were one setting away from obvious, and the clue was the sidechain
source itself being the only compressor control that responded.

**LFO 3 escapes every CC-based stabilisation, because it has no CC.** Track
1 measured a floor of 6.84 against itself -- as different from itself as an
unrelated sound -- with LFO 1 and LFO 2 silenced by CC and LFO 3 left free
running. Zeroing its depth over NRPN 1:72 took the floor to 0.045, a
150-fold improvement, and made the track measurable at all. Anything that
needs a repeatable voice has to silence LFO 3 over NRPN.

A related trap: CC 62 and 63 cannot be stabilised generically. They are
oscillator reset on FM DRUM but noise type and character on WAVETONE, so
setting them blindly steadies one machine and destabilises another --
setting them raised track 1's floor from 0.045 to 0.21 by switching its
noise on.

## The send effects, checked by their physics

`tools/check_effects.py` asks whether an effect does what its name says
rather than merely something, across a range of settings:

| control | prediction | measured |
|---|---|---|
| DELAY TIME | echo spacing tracks the setting | 20 -> 232 ms, 45 -> 507 ms, 70 -> 783 ms |
| DELAY FEEDBACK | more repeats | 4 -> 10 bursts |
| REVERB DECAY | longer tail | late energy 0.0035 -> 0.1449, rho +1.000 |

The delay is linear at about 11 ms per unit -- two consecutive steps of 25
gave 275 ms and 276 ms. That is arithmetic, not "the sound changed".

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
- **Measure each descriptor's floor too, don't assume it.** How far a
  descriptor wanders between two recordings of the same patch depends
  entirely on the material: a quiet decaying tail wanders far more than a
  struck note. Fixed tolerances were a guess; measured ones let a
  descriptor carry the verdict where the spectral distance cannot.
- **Compare the part of the note the parameter acts on.** A filter's
  release happens after the key is up and a hold stage only in the plateau
  before decay, so comparing the whole note buries either in the noise.
  `amp.hold` read 0.075 across the whole note and 0.440 windowed past the
  transient -- which is identical either way and was doing nothing but
  diluting the measurement.
- **Some parameters need two notes.** An envelope reset only acts when a
  new trig arrives, so a single-note probe cannot show it at all.
- **Expect the audio device to refuse occasionally.** Polling for silence
  opens it several thousand times across a sweep and CoreAudio turns one
  down now and then. Backing off beats losing the run; the cost is one
  noisier reading, which the noise floor already accounts for.
- **A parameter is only audible if what it feeds is on.** A bipolar depth
  at raw 64 is zero depth, and an LFO with no destination cannot make its
  own speed or waveform heard. Thirty parameters first read as inaudible
  for that reason alone.
- **A parameter verified in any pass is verified.** The baseline that
  reveals one can mask another: turning an LFO's depth up to expose its
  waveform leaves the depth itself near its limit.

## Six wrong answers the harness gave before it was trusted

Every one was in the measurement, none in the map. They are listed because
each is a way a verification harness can produce confident nonsense:

- **The spectral distance is level-invariant.** `mstft_distance`
  RMS-normalises both signals, so a volume, a send or a compressor mix is
  invisible to it. The one case where it appeared to catch a level change
  was silence, where normalising divides by epsilon.
- **Descriptor evidence was taken from one probe value only** -- whichever
  moved the spectrum most -- so a parameter that changed the level at the
  other end had that evidence collected and thrown away.
- **Probes went to the wrong MIDI channel.** Resolved correctly when
  sending the patch and not when sending the probe, so every send-effect
  parameter landed on the track channel. It made the pattern volume read as
  inert and an unconnected external input read as responding.
- **Every recording was truncated 700 ms after the onset**, which discards
  exactly what an effect does. Delay echoes landed past the cut and reverb
  T20 read 55 ms at every decay setting.
- **Rank correlation passed a flat response.** Tied values were given
  distinct ranks, so a dead control scored a perfect 1.0; and near-ties
  from noise in the decimals scored +0.949. Each check now requires the
  measurement to move as well as rank.
- **The echo search stopped at 900 ms**, so the two longest delay settings
  read as no echo at all and pulled the correlation negative while the
  device was tracking perfectly.

Two process failures behind those: `str.replace` against a pattern an
earlier edit had already changed does nothing, and twice a fix announced as
applied was never in the file. Every edit now asserts its replacement
landed. And `pkill` killed the `uv` wrapper while leaving Python children
alive, so three sweeps ran at once on one MIDI port; a single-instance lock
and signal handling now prevent both the corruption and leaving the
instrument silent.

## Not yet verified

The Analog Heat, Analog Rytm MKII and Octatrack MKII maps are tested
transcriptions with no hardware check — none was connected. The sweep runs
against any of them once they are.

Also unverified: the Digitone's other machines. Switching machine needs a
hand on the device, since the Digitone II exposes no CC or NRPN for machine
selection.
