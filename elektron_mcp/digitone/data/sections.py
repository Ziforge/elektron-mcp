"""
Flat registry of every Digitone II parameter, keyed by section.

The per-machine data modules describe parameters in the shape the hardware
presents them (paged for synth machines, flat for filters/amp/fx/LFO). Tools
need one flat namespace per section instead, so this module does that
flattening once and guarantees the resulting Python identifiers are unique
within a section.
"""

# to_identifier is shared with the other instrument servers:
# verified to produce identical results across all 210 labels
# in the Digitone and Rytm maps before the local copy was
# removed.
from rig_midi.params import to_identifier

from elektron_mcp.digitone.data.amp import AMP_PARAMS_DATA
from elektron_mcp.digitone.data.filters import (
    MULTI_MODE_FILTER_PARAMS,
    LOWPASS_4_FILTER_PARAMS,
    EQUALIZER_FILTER_PARAMS,
    BASE_WIDTH_FILTER_PARAMS,
    LEGACY_LP_HP_FILTER_PARAMS,
    COMB_MINUS_FILTER_PARAMS,
    COMB_PLUS_FILTER_PARAMS,
)
from elektron_mcp.digitone.data.fm_drum import FM_DRUM_PARAMS
from elektron_mcp.digitone.data.fm_tone import FM_TONE_PARAMS
from elektron_mcp.digitone.data.fx import FX_PARAMS_DATA
from elektron_mcp.digitone.data.lfo import LFO1_PARAMS, LFO2_PARAMS, LFO3_PARAMS
from elektron_mcp.digitone.data.swarmer import SWARMER_PARAMS
from elektron_mcp.digitone.data.wavetone import WAVETONE_PARAMS


def _walk(node: dict, page: str, path: tuple, out: dict) -> None:
    """Recursively collect leaf parameters (those carrying a cc_msb)."""
    for label, spec in node.items():
        if not isinstance(spec, dict):
            continue
        if "cc_msb" in spec:
            here = path + (label,)
            ident = "_".join(to_identifier(p) for p in here)
            if ident in out:
                # Same label on two pages: disambiguate by page number.
                ident = f"{ident}_p{page.rsplit('_', 1)[-1]}"
            if ident in out:
                raise ValueError(f"duplicate identifier {ident!r} in {page}")
            out[ident] = dict(
                spec, _page=page, _label=".".join(here)
            )
        else:
            # A nested group, e.g. page_2 "A" holding atk/dec/end/lev.
            _walk(spec, page, path + (label,), out)


def _flatten(params: dict) -> dict:
    """Flatten a possibly paged, possibly nested parameter map.

    Returns {identifier: spec}, where each spec keeps its source page and
    dotted hardware label so errors and the reference tool can point back at
    the manual.
    """
    is_paged = all(
        isinstance(v, dict) and "cc_msb" not in v and bool(v)
        and all(isinstance(x, dict) for x in v.values())
        for v in params.values()
    ) and all(k.startswith("page_") for k in params)

    pages = params if is_paged else {"page_1": params}

    flat: dict = {}
    for page, page_params in pages.items():
        _walk(page_params, page, (), flat)
    return flat


SECTIONS: dict[str, dict] = {
    "fm_drum": _flatten(FM_DRUM_PARAMS),
    "fm_tone": _flatten(FM_TONE_PARAMS),
    "swarmer": _flatten(SWARMER_PARAMS),
    "wavetone": _flatten(WAVETONE_PARAMS),
    "amp": _flatten(AMP_PARAMS_DATA),
    "fx": _flatten(FX_PARAMS_DATA),
    "lfo1": _flatten(LFO1_PARAMS),
    "lfo2": _flatten(LFO2_PARAMS),
    "lfo3": _flatten(LFO3_PARAMS),
    "filter_multi_mode": _flatten(MULTI_MODE_FILTER_PARAMS),
    "filter_lowpass4": _flatten(LOWPASS_4_FILTER_PARAMS),
    "filter_equalizer": _flatten(EQUALIZER_FILTER_PARAMS),
    "filter_base_width": _flatten(BASE_WIDTH_FILTER_PARAMS),
    "filter_legacy_lp_hp": _flatten(LEGACY_LP_HP_FILTER_PARAMS),
    "filter_comb_minus": _flatten(COMB_MINUS_FILTER_PARAMS),
    "filter_comb_plus": _flatten(COMB_PLUS_FILTER_PARAMS),
}

# Sections whose filter type must be selected on the device before its
# parameters respond; surfaced in tool docstrings.
MACHINE_SECTIONS = ("fm_drum", "fm_tone", "swarmer", "wavetone")
