"""
Analog Rytm MKII parameter map.

Originally transcribed from the Cirklon instrument definitions in
github.com/Ziforge/CirklonSynthDefs (RytmMKII, RytmMKII-FX, RytmMKII-Perf),
then checked against Appendix C of the Analog Rytm MKII manual, OS 1.74.
The appendix confirmed every CC already here and added the three trig
parameters below. The map is CC-only, so the section tools degrade to CC
when asked for NRPN.

The eight SYNTH CCs, 16 to 23, are machine-dependent: each machine names
them differently. See rytm.machines for the per-machine names.

Channel layout: the twelve drum tracks sit on MIDI channels 1-12, the FX
block on channel 13 and the performance macros on channel 14. The sections
below say which channel they expect.

Unlike the Digitone II, the Rytm exposes machine selection as a CC (15,
Track Machine), so a track's machine can be set over MIDI rather than by
hand on the device.
"""


def _p(cc: int, label: str, **kw) -> dict:
    spec = {"cc_msb": cc, "_label": label, "_page": "rytm"}
    spec.update(kw)
    return spec


# --- Per-track sections, MIDI channels 1-12 ---------------------------------

RYTM_SYNTH = {
    "trk_mch": _p(15, "TrkMch"),
    "syn1": _p(16, "Syn1"),
    "syn2": _p(17, "Syn2"),
    "syn3": _p(18, "Syn3"),
    "syn4": _p(19, "Syn4"),
    "syn5": _p(20, "Syn5"),
    "syn6": _p(21, "Syn6"),
    "syn7": _p(22, "Syn7"),
    "syn8": _p(23, "Syn8"),
}

RYTM_SAMPLE = {
    "tune": _p(24, "SmpTun"),
    "fine_tune": _p(25, "SmpFnT"),
    "bit_reduction": _p(26, "SmpBit"),
    "slot": _p(27, "SmpSlt"),
    "start": _p(28, "SmpStr"),
    "end": _p(29, "SmpEnd"),
    "loop": _p(30, "SmpLp"),
    "level": _p(31, "SmpLvl"),
}

RYTM_FILTER = {
    "atk": _p(70, "FltAtk"),
    "dec": _p(71, "FltDec"),
    "sus": _p(72, "FltSus"),
    "rel": _p(73, "FltRel"),
    "freq": _p(74, "FltFrq"),
    "reso": _p(75, "FltRes"),
    "mode": _p(76, "FltMod"),
    "env_depth": _p(77, "FltEnv"),
}

RYTM_AMP = {
    "atk": _p(78, "AmpAtk"),
    "hold": _p(79, "AmpHld"),
    "dec": _p(80, "AmpDec"),
    "overdrive": _p(81, "AmpOD"),
    "delay_send": _p(82, "AmpDly"),
    "reverb_send": _p(83, "AmpRev"),
    "vol": _p(7, "AmpVol"),
    "pan": _p(10, "AmpPan"),
}

RYTM_LFO = {
    "spd": _p(102, "LfoSpd"),
    "mult": _p(103, "LfoMul"),
    "fade": _p(104, "LfoFad"),
    "dest": _p(105, "LfoDst"),
    "wave": _p(106, "LfoWav"),
    "start_phase": _p(107, "LfoStr"),
    "trig_mode": _p(108, "LfoTrg"),
    # The only high-resolution parameter on the Rytm: CC 109 is the coarse
    # half, CC 118 the fine one.
    "depth": _p(109, "LfoDep", cc_lsb=118),
}

RYTM_TRACK = {
    "level": _p(95, "TrkLvl"),
    "mute": _p(94, "TrkMut"),
    "solo": _p(93, "TrkSol"),
    "active_scene": _p(92, "ActScn"),
}

# CC 3, 4 and 5 carry the trig's own note, velocity and length, which is
# how a sequencer plays a track rather than just shaping its sound.
RYTM_TRIG = {
    "note": _p(3, "Note"),
    "velocity": _p(4, "Vel"),
    "length": _p(5, "Length"),
    "syn_trig": _p(11, "SynTrg"),
    "smp_trig": _p(12, "SmpTrg"),
    "env_trig": _p(13, "EnvTrg"),
    "lfo_trig": _p(14, "LfoTrg"),
}

RYTM_EUCLID = {
    "pulse_gen_a": _p(86, "PlsGen"),
    "pulse_gen_b": _p(87, "PlsGen"),
    "bool_op": _p(88, "BoolOp"),
    "rot_gen_a": _p(89, "RotGen"),
    "rot_gen_b": _p(90, "RotGen"),
    "track_rotation": _p(91, "TrkRot"),
    # The committed .cki truncates "EucOn/Off" to six characters
    # as "EucOn/"; keep that on the Cirklon, and the cleaner
    # form in the tools.
    "euclid_on": _p(117, "EucOn", cki_label="EucOn/"),
}

# --- FX block, MIDI channel 13 ---------------------------------------------

RYTM_FX = {
    "delay_time": _p(16, "DlyTm"),
    "delay_ping_pong": _p(17, "DlyPP"),
    "delay_stereo_width": _p(18, "DlyStW"),
    "delay_feedback": _p(19, "DlyFB"),
    "delay_hpf": _p(20, "DlyHPF"),
    "delay_lpf": _p(21, "DlyLPF"),
    "delay_to_reverb": _p(22, "DlyRev"),
    "delay_mix": _p(23, "DlyMix"),
    "reverb_predelay": _p(24, "RevPre"),
    "reverb_decay": _p(25, "RevDec"),
    "reverb_shelf_freq": _p(26, "RevShl"),
    "reverb_shelf_gain": _p(27, "RevShl"),
    "reverb_hpf": _p(28, "RevHPF"),
    "reverb_lpf": _p(29, "RevLPF"),
    "reverb_mix": _p(31, "RevMix"),
    "dist_amount": _p(70, "DistAm"),
    "dist_symmetry": _p(71, "DistSy"),
    "delay_overdrive": _p(72, "DlyOD"),
    "delay_dist_routing": _p(76, "DlyDis"),
    "reverb_dist_routing": _p(77, "RevDis"),
    "comp_threshold": _p(78, "CompTh"),
    "comp_attack": _p(79, "CompAt"),
    "comp_release": _p(80, "CompRe"),
    "comp_makeup": _p(81, "CompMa"),
    "comp_ratio": _p(82, "CompRa"),
    "comp_sidechain": _p(83, "CompSi"),
    "comp_dry_wet": _p(84, "CompDr"),
    "comp_output": _p(85, "CompOu"),
}

# --- Performance macros, MIDI channel 14 -----------------------------------
# CC 38 is deliberately skipped: it is NRPN data entry LSB.

RYTM_PERF = {
    f"perf{i}": _p(cc, f"Perf{i}")
    for i, cc in enumerate(
        [35, 36, 37, 39, 40, 41, 42, 43, 44, 45, 46, 47], start=1
    )
}

RYTM_SECTIONS: dict[str, dict] = {
    "rytm_synth": RYTM_SYNTH,
    "rytm_sample": RYTM_SAMPLE,
    "rytm_filter": RYTM_FILTER,
    "rytm_amp": RYTM_AMP,
    "rytm_lfo": RYTM_LFO,
    "rytm_track": RYTM_TRACK,
    "rytm_trig": RYTM_TRIG,
    "rytm_euclid": RYTM_EUCLID,
    "rytm_fx": RYTM_FX,
    "rytm_perf": RYTM_PERF,
}

# Expected MIDI channel per section, for tool docstrings.
RYTM_CHANNELS = {
    "rytm_fx": 13,
    "rytm_perf": 14,
}

RYTM_NOTES = {
    "rytm_synth": (
        "Parameters syn1-syn8 are machine dependent: what each one controls "
        "depends on the track's machine. Unlike the Digitone II, the machine "
        "itself is settable here over MIDI via trk_mch (CC 15)."
    ),
    "rytm_fx": "Send on MIDI channel 13, the Rytm's FX channel.",
    "rytm_perf": "Send on MIDI channel 14, the Rytm's performance channel.",
}
