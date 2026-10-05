"""
Analog Rytm MKII machines: the per-machine SYNTH parameter names.

Every machine drives the same eight CCs, 16 to 23, but each names them
differently -- the manual says so explicitly: "the order of the SYNTH
parameters below will sometimes differ from the order of the parameters
shown on the SRC page". So a single instrument definition cannot describe
the Rytm; it needs one per machine.

Transcribed from the Analog Rytm MKII manual, OS 1.74:

- Appendix C.8 MACHINE PARAMETERS gives the CC number and full name.
- Appendix D: MACHINES gives the three- or four-character label the device
  itself shows on screen, which is what the Cirklon's six-character display
  wants. The two appendices sometimes use different names for the same
  parameter (Appendix C's "Transient Tick" is Appendix D's TIC, "Body
  Decay" is BDY), so the labels here are matched by meaning, not position.

Every label comes from the manual. None is invented.

Machines use a contiguous run of CCs from 16, but not all use all eight:
UT IMPULSE has four, CH METALLIC three.
"""

# machine name -> (cirklon display name, [(cc, full name, screen label)])
MACHINES = {
    'BD PLASTIC': (
        'BD Plastic',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay Time', 'BDY'),
            (19, 'Sweep Depth', 'SWD'),
            (20, 'Sweep Time', 'SWT'),
            (21, 'Hold Time', 'HLD'),
            (22, 'VCO Click', 'CLK'),
            (23, 'Dust Level', 'DUS'),
        ],
    ),
    'BD SHARP': (
        'BD Sharp',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'Sweep Depth', 'SWD'),
            (20, 'Sweep Time', 'SWT'),
            (21, 'Hold Time', 'HLD'),
            (22, 'Tick Level', 'TIC'),
            (23, 'Waveform', 'WAV'),
        ],
    ),
    'BD HARD': (
        'BD Hard',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'Hold', 'HLD'),
            (20, 'Sweep Time', 'SWT'),
            (21, 'Sweep Depth', 'SWD'),
            (22, 'Waveform', 'WAV'),
            (23, 'Transient Tick', 'TIC'),
        ],
    ),
    'BD CLASSIC': (
        'BD Classic',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'Hold', 'HLD'),
            (20, 'Sweep Time', 'SWT'),
            (21, 'Sweep Depth', 'SWD'),
            (22, 'Waveform', 'WAV'),
            (23, 'Transient Tick', 'TIC'),
        ],
    ),
    'BD FM': (
        'BD FM',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'FM Amount', 'FMA'),
            (20, 'Sweep Time', 'SWT'),
            (21, 'FM Sweep Time', 'FMS'),
            (22, 'FM Decay Time', 'FMD'),
            (23, 'FM Tune', 'FMT'),
        ],
    ),
    'BD SILKY': (
        'BD Silky',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'Sweep Depth', 'SWD'),
            (20, 'Sweep Time', 'SWT'),
            (21, 'Hold', 'HLD'),
            (22, 'VCO Click', 'CLK'),
            (23, 'Dust Level', 'DUS'),
        ],
    ),
    'BD ACOUSTIC': (
        'BD Acoustic',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'Sweep Depth', 'SWD'),
            (20, 'Sweep Time', 'SWT'),
            (21, 'Hold Time', 'HLD'),
            (22, 'Impact', 'IMP'),
            (23, 'Waveform', 'WAV'),
        ],
    ),
    'SD NATURAL': (
        'SD Natural',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Body Decay', 'BDY'),
            (19, 'Noise Decay', 'NOD'),
            (20, 'Noise LPF', 'LPF'),
            (21, 'Noise Balance', 'BAL'),
            (22, 'Noise Resonance', 'RES'),
            (23, 'Noise HPF', 'HPF'),
        ],
    ),
    'SD HARD': (
        'SD Hard',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'Sweep Depth', 'SWD'),
            (20, 'Tick Level', 'TIC'),
            (21, 'Noise Decay', 'NOD'),
            (22, 'Noise Level', 'NOL'),
            (23, 'Sweep Time', 'SWT'),
        ],
    ),
    'SD CLASSIC': (
        'SD Classic',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'Detune', 'DET'),
            (20, 'Snap Amount', 'SNP'),
            (21, 'Noise Decay', 'NOD'),
            (22, 'Noise Level', 'NOL'),
            (23, 'Osc Balance', 'BAL'),
        ],
    ),
    'SD FM': (
        'SD FM',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'FM Tune', 'FMT'),
            (20, 'FM Decay Time', 'FMD'),
            (21, 'Noise Decay', 'NOD'),
            (22, 'Noise Level', 'NOL'),
            (23, 'FM Amount', 'FMA'),
        ],
    ),
    'SD ACOUSTIC': (
        'SD Acoustic',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'Noise Decay', 'NOD'),
            (20, 'Hold Time', 'HLD'),
            (21, 'Noise Level', 'NOL'),
            (22, 'Impact', 'IMP'),
            (23, 'Sweep Depth', 'SWD'),
        ],
    ),
    'RS HARD': (
        'RS Hard',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'Sweep Depth', 'SWD'),
            (20, 'Tick Level', 'TIC'),
            (21, 'Noise Level', 'NOL'),
            (22, 'Symmetry', 'SYM'),
            (23, 'Sweep Time', 'SWT'),
        ],
    ),
    'RS CLASSIC': (
        'RS Classic',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune Osc 1', 'T1'),
            (18, 'Decay', 'DEC'),
            (19, 'Osc Balance', 'BAL'),
            (20, 'Tune Osc 2', 'T2'),
            (21, 'Symmetry', 'SYM'),
            (22, 'Noise Level', 'NOL'),
            (23, 'Tick Level', 'TIC'),
        ],
    ),
    'CP CLASSIC': (
        'CP Classic',
        [
            (16, 'Level', 'LEV'),
            (17, 'Noise Tone', 'TON'),
            (18, 'Noise Decay', 'NOD'),
            (19, 'Clap Number', 'NUM'),
            (20, 'Clap Rate', 'RAT'),
            (21, 'Noise Level', 'NOL'),
            (22, 'Random Claps', 'RND'),
            (23, 'Clap Decay', 'CPD'),
        ],
    ),
    'SY DUAL VCO': (
        'SY DualVCO',
        [
            (16, 'Level', 'LEV'),
            (17, 'Osc 1 Tune', 'TUNE'),
            (18, 'Osc 1 Decay', 'DEC'),
            (19, 'Balance', 'BAL'),
            (20, 'Osc 2 Detune', 'DET'),
            (21, 'Osc Config', 'CFG'),
            (22, 'Osc 2 Decay', 'DEC2'),
            (23, 'Bend', 'BND'),
        ],
    ),
    'SY CHIP': (
        'SY Chip',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'Waveform', 'WAV'),
            (20, 'Speed', 'SPD'),
            (21, 'Offset 2', 'OF2'),
            (22, 'Offset 3', 'OF3'),
            (23, 'Offset 4', 'OF4'),
        ],
    ),
    'SY RAW': (
        'SY Raw',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'Noise Level', 'NOL'),
            (20, 'Osc 2 Detune', 'DET'),
            (21, 'Waveform 1', 'WAV1'),
            (22, 'Waveform 2', 'WAV2'),
            (23, 'Balance', 'BAL'),
        ],
    ),
    'BT CLASSIC': (
        'BT Classic',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'Sweep Depth', 'SWD'),
            (20, 'Noise Level', 'NOL'),
            (21, 'Snap Type', 'SNP'),
        ],
    ),
    'LT, MT, HT CLASSIC': (
        'Tom Classic',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'Sweep Depth', 'SWD'),
            (20, 'Sweep Time', 'SWT'),
            (21, 'Noise Decay', 'NOD'),
            (22, 'Noise Level', 'NOL'),
            (23, 'Noise Tone', 'TON'),
        ],
    ),
    'CH CLASSIC': (
        'CH Classic',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'Color', 'COL'),
        ],
    ),
    'CH METALLIC': (
        'CH Metallic',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay Time', 'BDY'),
        ],
    ),
    'OH CLASSIC': (
        'OH Classic',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'Color', 'COL'),
        ],
    ),
    'OH METALLIC': (
        'OH Metallic',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay Time', 'BDY'),
        ],
    ),
    'HH BASIC': (
        'HH Basic',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay Time', 'BDY'),
            (19, 'Tone', 'TON'),
            (20, 'Transient Decay', 'TRD'),
            (21, 'Osc Reset', 'RST'),
        ],
    ),
    'HH LAB': (
        'HH Lab',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune 1', 'OSC1'),
            (18, 'Decay Time', 'BDY'),
            (19, 'Tune 2', 'OSC2'),
            (20, 'Tune 3', 'OSC3'),
            (21, 'Tune 4', 'OSC4'),
            (22, 'Tune 5', 'OSC5'),
            (23, 'Tune 6', 'OSC6'),
        ],
    ),
    'CY METALLIC': (
        'CY Metallic',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay Time', 'BDY'),
            (19, 'Tone', 'TON'),
            (20, 'Transient Decay', 'TRD'),
        ],
    ),
    'CY CLASSIC': (
        'CY Classic',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay', 'DEC'),
            (19, 'Color', 'COL'),
            (20, 'Tone', 'TON'),
        ],
    ),
    'CY RIDE': (
        'CY Ride',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Tail Decay', 'DEC'),
            (19, 'Hit Decay', 'HIT'),
            (20, 'Cymbal Type', 'TYP'),
            (21, 'Component 1', 'C1'),
            (22, 'Component 2', 'C2'),
            (23, 'Component 3', 'C3'),
        ],
    ),
    'CB CLASSIC & METALLIC': (
        'CB Cls+Met',
        [
            (16, 'Level', 'LEV'),
            (17, 'Tune', 'TUN'),
            (18, 'Decay Time', 'BDY'),
            (19, 'Detune', 'DET'),
        ],
    ),
    'UT NOISE': (
        'UT Noise',
        [
            (16, 'Level', 'LEV'),
            (17, 'LP Frequency', 'LPF'),
            (18, 'Decay', 'DEC'),
            (19, 'Sweep Depth', 'SWD'),
            (20, 'Sweep Time', 'SWT'),
            (21, 'LP Resonance', 'LPQ'),
            (22, 'HP Frequency', 'HPF'),
            (23, 'Attack', 'ATK'),
        ],
    ),
    'UT IMPULSE': (
        'UT Impulse',
        [
            (16, 'Level', 'LEV'),
            (17, 'Attack', 'ATK'),
            (18, 'Decay', 'DEC'),
            (19, 'Polarity', 'POL'),
        ],
    ),
}


# Which track types each machine family belongs to, for grouping the
# generated instrument definitions into files.
FAMILIES = {
    'BD': 'BD',
    'SD': 'SD',
    'RS': 'RS',
    'CP': 'CP',
    'SY': 'SY',
    'BT': 'BT',
    'LT': 'Tom',
    'CH': 'CH',
    'OH': 'OH',
    'HH': 'HH',
    'CY': 'CY',
    'CB': 'CB',
    'UT': 'UT'
}


def family(machine: str) -> str:
    """The track-type family a machine belongs to."""
    return FAMILIES[machine.split()[0].rstrip(',')]


def display_name(machine: str) -> str:
    """The Cirklon instrument name for a machine, within its 16 characters."""
    return f"Rytm {MACHINES[machine][0]}"
