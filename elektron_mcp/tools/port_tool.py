"""
MIDI port handover tools.

Only one process can hold the instrument's MIDI port. While this server has
it, other tools on the same machine -- Elektroid, Elektron Transfer, a DAW --
get silence or a handshake timeout rather than an obvious error. Releasing
the port without stopping the server makes that handover explicit instead of
requiring a restart.
"""


def register_port_tools(mcp, midi):
    """Register port release/reacquire tools with the MCP server."""

    @mcp.tool()
    def release_midi_port() -> dict:
        """
        Release the instrument's MIDI port so another program can use it.

        Use before running Elektroid, Elektron Transfer or anything else that
        needs SysEx access: while this server holds the port, their device
        handshake times out and they silently fall back to generic MIDI.

        No parameter tool will work until reconnect_midi_port is called.

        Returns:
            dict: Which port was released.
        """
        name = midi.output_port_name
        if not midi.connected:
            return {"released": False, "note": "no port was open"}
        midi.disconnect()
        return {
            "released": True,
            "port": name,
            "note": "parameter and note tools are inert until "
            "reconnect_midi_port is called",
        }

    @mcp.tool()
    def reconnect_midi_port(port_name: str | None = None) -> dict:
        """
        Reacquire the instrument's MIDI port after releasing it.

        Args:
            port_name: Port to open, or omit to reuse the previous one and
                otherwise auto-detect.

        Returns:
            dict: Whether the port is open, and which one.
        """
        if midi.connected:
            return {"connected": True, "port": midi.output_port_name,
                    "note": "already connected"}

        target = port_name or midi.output_port_name
        ok = midi.connect(target) if target else midi.auto_connect()
        return {
            "connected": bool(ok),
            "port": midi.output_port_name,
            "ports": midi.list_ports() if not ok else None,
        }

    @mcp.tool()
    def midi_port_status() -> dict:
        """
        Report whether this server currently holds the MIDI port.

        Returns:
            dict: Connection state, port name, and the ports available.
        """
        return {
            "connected": bool(midi.connected),
            "port": midi.output_port_name,
            "input_open": midi.input_port is not None,
            "available_ports": midi.list_ports(),
        }
