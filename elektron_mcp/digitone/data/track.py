"""
Digitone II per-track parameters that are not part of a machine.

From Appendix C of the manual, OS 1.12: C.1 TRACK, C.2 TRIG, C.6 EUCLIDEAN
and the pattern mute from C.12. These sit on the same MIDI channel as the
track's machine and filter -- the one set under
SETTINGS > MIDI CONFIG > CHANNELS > TRACK 1-16.

The euclidean sequencer is NRPN-only: Appendix C.6 leaves the CC column
empty for all seven of its parameters, as it does for LFO 3.

Field naming follows the rest of this package, where `nrpn_lsb` holds the
parameter bank the manual calls the NRPN MSB.
"""

# C.2 TRIG PARAMETERS. Note, velocity and length are how a sequencer plays
# a track rather than just shapes it. Filter Trig and LFO Trig have no NRPN
# number in the appendix.
TRIG_PARAMS = {
    "NOTE": {"cc_msb": 3, "nrpn_lsb": 3, "nrpn_msb": 0},
    "VEL": {"cc_msb": 4, "nrpn_lsb": 3, "nrpn_msb": 1,
            "default": 100},
    "LEN": {"cc_msb": 5, "nrpn_lsb": 3, "nrpn_msb": 2},
    "FLTR.Trig": {"cc_msb": 13, "max_midi": 1, "max_val": 1,
                  "default": 1, "options": ["off", "on"]},
    "LFO.Trig": {"cc_msb": 14, "max_midi": 1, "max_val": 1,
                 "default": 1, "options": ["off", "on"]},
    "PORT.Time": {"cc_msb": 9, "nrpn_lsb": 3, "nrpn_msb": 6},
    "PORT.On": {"cc_msb": 65, "nrpn_lsb": 3, "nrpn_msb": 7,
                "max_midi": 1, "max_val": 1, "default": 0,
                "options": ["off", "on"]},
}

# C.1 TRACK PARAMETERS.
TRACK_PARAMS = {
    "MUTE": {"cc_msb": 94, "nrpn_lsb": 1, "nrpn_msb": 108,
             "max_midi": 1, "max_val": 1, "default": 0,
             "options": ["unmuted", "muted"]},
    "LEVEL": {"cc_msb": 95, "nrpn_lsb": 1, "nrpn_msb": 110,
              "default": 100},
}

# C.6 EUCLIDEAN SEQUENCER PARAMETERS -- NRPN only, no CC at all.
EUCLID_PARAMS = {
    "PL1": {"nrpn_lsb": 3, "nrpn_msb": 8},
    "PL2": {"nrpn_lsb": 3, "nrpn_msb": 9},
    "BOOL": {"nrpn_lsb": 3, "nrpn_msb": 10},
    "RO1": {"nrpn_lsb": 3, "nrpn_msb": 11},
    "RO2": {"nrpn_lsb": 3, "nrpn_msb": 12},
    "TRO": {"nrpn_lsb": 3, "nrpn_msb": 13},
    "EUC": {"nrpn_lsb": 3, "nrpn_msb": 14, "max_midi": 1,
            "max_val": 1, "default": 0, "options": ["off", "on"]},
}

# C.12 MISC. Pattern mute is per-track; master overdrive lives on the FX
# control channel and is in global_fx.py with the rest of that block.
MISC_PARAMS = {
    "PAT.Mute": {"cc_msb": 110, "nrpn_lsb": 1, "nrpn_msb": 109,
                 "max_midi": 1, "max_val": 1, "default": 0,
                 "options": ["unmuted", "muted"]},
}
