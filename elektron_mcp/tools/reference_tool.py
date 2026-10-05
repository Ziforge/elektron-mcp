"""
Parameter reference tools.

The batch tools document their own arguments, but a model designing a patch
often wants the whole section laid out at once -- CC numbers, display ranges,
defaults and enum options together -- before deciding what to send.
"""

from elektron_mcp.digitone.data.sections import SECTIONS, MACHINE_SECTIONS


def register_reference_tools(mcp, midi):
    """Register parameter discovery tools with the MCP server."""

    @mcp.tool()
    def list_sections() -> dict:
        """
        List every controllable Digitone II section and its parameter count.

        Machine sections need the matching machine selected on the track
        before their parameters respond.

        Returns:
            dict: Section names mapped to parameter count and whether the
            section is a synth machine.
        """
        return {
            "sections": {
                name: {
                    "parameters": len(params),
                    "is_machine": name in MACHINE_SECTIONS,
                }
                for name, params in SECTIONS.items()
            },
            "total_parameters": sum(len(p) for p in SECTIONS.values()),
        }

    @mcp.tool()
    def get_param_reference(section: str) -> dict:
        """
        Get the full parameter table for one section.

        Args:
            section (str): Section name as returned by list_sections, e.g.
                'fm_drum', 'filter_base_width', 'lfo1'.

        Returns:
            dict: Each parameter mapped to its CC number, hardware label,
            page, raw MIDI range, display range, default and enum options.
        """
        if section not in SECTIONS:
            return {
                "error": f"unknown section {section!r}",
                "available": sorted(SECTIONS),
            }

        table = {}
        for ident, spec in SECTIONS[section].items():
            entry = {
                "cc": int(spec["cc_msb"]) if "cc_msb" in spec else None,
                "nrpn": (f'{int(spec["nrpn_lsb"])}:{int(spec["nrpn_msb"])}'
                         if "nrpn_msb" in spec else None),
                "label": spec.get("_label", ident),
                "page": spec.get("_page"),
                "midi_range": [spec.get("min_midi", 0), spec.get("max_midi", 127)],
                "display_range": [spec.get("min_val", 0), spec.get("max_val", 127)],
                "default": spec.get("default"),
            }
            if spec.get("options"):
                entry["options"] = spec["options"]
            table[ident] = entry

        return {
            "section": section,
            "is_machine": section in MACHINE_SECTIONS,
            "parameters": table,
        }
