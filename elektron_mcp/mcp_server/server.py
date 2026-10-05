"""
MCP server configuration and initialization.
"""

from mcp.server.fastmcp import FastMCP

from elektron_mcp.midi.digitone_midi import DigitoneMIDI
from elektron_mcp.tools.lfo_tool import register_lfo_tools
from elektron_mcp.tools.wavetone_tool import register_wavetone_tools
from elektron_mcp.tools.filter_tool import register_filter_tools
from elektron_mcp.tools.amp_tool import register_amp_tools
from elektron_mcp.tools.fx_tool import register_fx_tools
from elektron_mcp.tools.section_tool import register_section_tools
from elektron_mcp.tools.play_tool import register_play_tools
from elektron_mcp.tools.reference_tool import register_reference_tools
from elektron_mcp.tools.audition_tool import register_audition_tools
from elektron_mcp.tools.patch_tool import register_patch_tools
from elektron_mcp.tools.learn_tool import register_learn_tools
from elektron_mcp.rytm.data import RYTM_SECTIONS, RYTM_NOTES
from elektron_mcp.tools.port_tool import register_port_tools
from elektron_mcp.tools.preset_tool import register_preset_tools


# Initialize MCP and MIDI
mcp = FastMCP("Digitone 2")
midi = DigitoneMIDI()

# Register all tools
register_wavetone_tools(mcp, midi)
register_filter_tools(mcp, midi)
register_amp_tools(mcp, midi)
register_fx_tools(mcp, midi)
register_lfo_tools(mcp, midi)

# Batch parameter tools covering every section (all four machines, all seven
# filter types, amp, fx, LFO 1-3), plus note playback and discovery.
register_section_tools(mcp, midi)
register_play_tools(mcp, midi)
register_reference_tools(mcp, midi)

# Audition: trigger a sound, capture the Digitone's USB audio, describe it --
# so a patch can be measured rather than only reasoned about.
register_audition_tools(mcp, midi)
# Patch snapshot/recall/diff/morph/mutate, from the state this server sent.
register_patch_tools(mcp, midi)
# MIDI learn: let the hardware say what it actually emits.
register_learn_tools(mcp, midi)

# Analog Rytm MKII: same batch-tool machinery over its own parameter map.
# Tracks are MIDI channels 1-12, FX is channel 13, performance macros are 14.
register_section_tools(mcp, midi, RYTM_SECTIONS, RYTM_NOTES)

# Hand the MIDI port over to Elektroid/Transfer without stopping the server.
register_port_tools(mcp, midi)

# Preset and project transfer over Elektron SysEx, via the Elektroid CLI.
register_preset_tools(mcp, midi)

# Export the configured MCP server
__all__ = ["mcp"]
