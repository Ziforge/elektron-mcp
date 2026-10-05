"""
Digitone II send effects and mixer, from Appendix C of the manual, OS 1.12.

These are not per-track. The manual is explicit: FX CONTROL CH "selects the
dedicated MIDI channel that is associated with the parameters on the DELAY,
REVERB, CHORUS, and COMPRESSOR parameter pages together with the master
overdrive, both for input and output" (13.4.3 CHANNELS). So every parameter
here is addressed on that one channel, not on a track's channel -- which is
also why their CC numbers are free to collide with the per-track ones.

Appendix C.9 for the send effects, C.10 for the mixer, C.12 for the master
overdrive. Field naming follows the rest of this package, where `nrpn_lsb`
holds the parameter bank the manual calls the NRPN MSB.
"""

# C.9 SEND FX: DELAY
DELAY_PARAMS = {
    "TIME": {"cc_msb": 21, "nrpn_lsb": 2, "nrpn_msb": 0},
    "PING": {"cc_msb": 22, "nrpn_lsb": 2, "nrpn_msb": 1,
             "max_midi": 1, "max_val": 1, "default": 0,
             "options": ["off", "on"]},
    "WID": {"cc_msb": 23, "nrpn_lsb": 2, "nrpn_msb": 2,
            "max_val": 63, "min_val": -64, "default": 0},
    "FDBK": {"cc_msb": 24, "nrpn_lsb": 2, "nrpn_msb": 3},
    "HPF": {"cc_msb": 25, "nrpn_lsb": 2, "nrpn_msb": 4},
    "LPF": {"cc_msb": 26, "nrpn_lsb": 2, "nrpn_msb": 5},
    "REV": {"cc_msb": 27, "nrpn_lsb": 2, "nrpn_msb": 6},
    "MIX": {"cc_msb": 28, "nrpn_lsb": 2, "nrpn_msb": 7},
}

# C.9 SEND FX: REVERB. Note the gap -- Mix Volume is NRPN 15, not 14.
REVERB_PARAMS = {
    "PRE": {"cc_msb": 29, "nrpn_lsb": 2, "nrpn_msb": 8},
    "DEC": {"cc_msb": 30, "nrpn_lsb": 2, "nrpn_msb": 9},
    "FREQ": {"cc_msb": 31, "nrpn_lsb": 2, "nrpn_msb": 10},
    "GAIN": {"cc_msb": 89, "nrpn_lsb": 2, "nrpn_msb": 11},
    "HPF": {"cc_msb": 90, "nrpn_lsb": 2, "nrpn_msb": 12},
    "LPF": {"cc_msb": 91, "nrpn_lsb": 2, "nrpn_msb": 13},
    "MIX": {"cc_msb": 92, "nrpn_lsb": 2, "nrpn_msb": 15},
}

# C.9 SEND FX: CHORUS
CHORUS_PARAMS = {
    "DEP": {"cc_msb": 16, "nrpn_lsb": 2, "nrpn_msb": 41},
    "SPD": {"cc_msb": 9, "nrpn_lsb": 2, "nrpn_msb": 42},
    "HPF": {"cc_msb": 70, "nrpn_lsb": 2, "nrpn_msb": 43},
    "WID": {"cc_msb": 71, "nrpn_lsb": 2, "nrpn_msb": 44},
    "DEL": {"cc_msb": 12, "nrpn_lsb": 2, "nrpn_msb": 45},
    "REV": {"cc_msb": 13, "nrpn_lsb": 2, "nrpn_msb": 46},
    "MIX": {"cc_msb": 14, "nrpn_lsb": 2, "nrpn_msb": 47},
}

# C.10 MIXER: COMPRESSOR, plus the pattern volume that shares its page.
COMPRESSOR_PARAMS = {
    "THR": {"cc_msb": 111, "nrpn_lsb": 2, "nrpn_msb": 16},
    "ATK": {"cc_msb": 112, "nrpn_lsb": 2, "nrpn_msb": 17},
    "REL": {"cc_msb": 113, "nrpn_lsb": 2, "nrpn_msb": 18},
    "MUP": {"cc_msb": 114, "nrpn_lsb": 2, "nrpn_msb": 19},
    "RAT": {"cc_msb": 115, "nrpn_lsb": 2, "nrpn_msb": 20},
    "SCS": {"cc_msb": 116, "nrpn_lsb": 2, "nrpn_msb": 21},
    "SCF": {"cc_msb": 117, "nrpn_lsb": 2, "nrpn_msb": 22},
    "MIX": {"cc_msb": 118, "nrpn_lsb": 2, "nrpn_msb": 23},
    "PAT.Vol": {"cc_msb": 119, "nrpn_lsb": 2, "nrpn_msb": 24,
                "default": 100},
}

# C.10 MIXER: EXTERNAL IN.
#
# The appendix lists each of these twice: once as separate Input L and
# Input R controls and again as a linked "Input L R" pair, on the same CC
# and NRPN numbers both times. They are two labels for one control,
# depending on whether DUAL MONO is on, so only one set is given here --
# naming both would put two identifiers on one CC and make setting either
# move the other.
EXTERNAL_IN_PARAMS = {
    "DUAL": {"cc_msb": 82, "nrpn_lsb": 2, "nrpn_msb": 40,
             "max_midi": 1, "max_val": 1, "default": 0,
             "options": ["stereo", "dual_mono"]},
    "L.Lvl": {"cc_msb": 72, "nrpn_lsb": 2, "nrpn_msb": 30},
    "R.Lvl": {"cc_msb": 73, "nrpn_lsb": 2, "nrpn_msb": 31},
    "L.Pan": {"cc_msb": 74, "nrpn_lsb": 2, "nrpn_msb": 32,
              "max_val": 63, "min_val": -64, "default": 0},
    "R.Pan": {"cc_msb": 75, "nrpn_lsb": 2, "nrpn_msb": 33,
              "max_val": 63, "min_val": -64, "default": 0},
    "L.Chorus": {"cc_msb": 76, "nrpn_lsb": 2, "nrpn_msb": 34},
    "R.Chorus": {"cc_msb": 77, "nrpn_lsb": 2, "nrpn_msb": 35},
    "L.Delay": {"cc_msb": 78, "nrpn_lsb": 2, "nrpn_msb": 36},
    "R.Delay": {"cc_msb": 79, "nrpn_lsb": 2, "nrpn_msb": 37},
    "L.Reverb": {"cc_msb": 80, "nrpn_lsb": 2, "nrpn_msb": 38},
    "R.Reverb": {"cc_msb": 81, "nrpn_lsb": 2, "nrpn_msb": 39},
}

# C.12 MISC: the master overdrive is on the FX control channel too.
MASTER_PARAMS = {
    "OVER": {"cc_msb": 17, "nrpn_lsb": 2, "nrpn_msb": 50},
}
