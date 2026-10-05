"""
Patch snapshot, recall, diff, morph and mutate tools.

The Digitone never reports its values back, so these work from what this
server has sent during the session. That makes them exact for parameters the
server owns and blind to anything turned on the hardware itself -- worth
knowing before trusting a snapshot as a complete sound.
"""

import random

from elektron_mcp.patches import store
from elektron_mcp.tools.section_tool import apply_sections


def register_patch_tools(mcp, midi):
    """Register patch management tools with the MCP server."""

    @mcp.tool()
    def get_track_state(track: int) -> dict:
        """
        Show every parameter value this server has sent to a track.

        Does not read the hardware -- anything changed on the device itself
        will not appear here.

        Args:
            track (int): Digitone track / MIDI channel, 1-16.

        Returns:
            dict: Sections mapped to parameter values, plus a total count.
        """
        state = store.TRACK_STATE.get(track)
        return {
            "track": track,
            "sections": state,
            "parameters": sum(len(v) for v in state.values()),
            "note": "reflects what this server sent, not a read of the device",
        }

    @mcp.tool()
    def snapshot_patch(name: str, track: int, note: str = "") -> dict:
        """
        Save the current tracked state of a track as a named patch.

        Args:
            name (str): Patch name. Letters, digits, spaces, dashes.
            track (int): Digitone track / MIDI channel, 1-16.
            note (str): Optional description to store alongside it.

        Returns:
            dict: Where it was written and how many parameters it holds.
        """
        state = store.TRACK_STATE.get(track)
        if not state:
            return {
                "error": f"nothing tracked for track {track}; set some "
                "parameters before snapshotting"
            }
        try:
            path = store.save(name, state, track, note)
        except ValueError as e:
            return {"error": str(e)}
        return {
            "saved": name,
            "path": path,
            "track": track,
            "parameters": sum(len(v) for v in state.values()),
        }

    @mcp.tool()
    def list_patches() -> dict:
        """
        List saved patches.

        Returns:
            dict: Each patch with its save time, source track, note and
            parameter count.
        """
        return {"patches": store.names(), "directory": str(store.PATCH_DIR)}

    @mcp.tool()
    def recall_patch(name: str, track: int, use_nrpn: bool = False) -> dict:
        """
        Send a saved patch to a track.

        The track's machine must already match the one the patch was designed
        for; recall sends parameter values, not machine selection.

        Args:
            name (str): Patch name as listed by list_patches.
            track (int): Digitone track / MIDI channel, 1-16.
            use_nrpn (bool): Send over 14-bit NRPN instead of 7-bit CC.

        Returns:
            dict: Per-section results of sending the patch.
        """
        try:
            patch = store.load(name)
        except FileNotFoundError as e:
            return {"error": str(e), "available": [p["name"] for p in store.names()]}
        return {
            "recalled": name,
            "designed_for_track": patch.get("source_track"),
            "result": apply_sections(midi, track, patch["sections"], use_nrpn),
        }

    @mcp.tool()
    def delete_patch(name: str) -> dict:
        """
        Delete a saved patch permanently.

        Args:
            name (str): Patch name as listed by list_patches.

        Returns:
            dict: Whether it existed and was removed.
        """
        try:
            removed = store.delete(name)
        except ValueError as e:
            return {"error": str(e)}
        return {"deleted": name} if removed else {"error": f"no patch named {name!r}"}

    @mcp.tool()
    def diff_patches(name_a: str, name_b: str) -> dict:
        """
        Compare two saved patches parameter by parameter.

        Args:
            name_a (str): First patch name.
            name_b (str): Second patch name.

        Returns:
            dict: Only the parameters that differ, each with from and to.
        """
        try:
            a, b = store.load(name_a), store.load(name_b)
        except FileNotFoundError as e:
            return {"error": str(e)}
        changes = store.diff(a["sections"], b["sections"])
        return {
            "a": name_a,
            "b": name_b,
            "changed": changes,
            "changed_count": sum(len(v) for v in changes.values()),
        }

    @mcp.tool()
    def morph_patches(
        name_a: str,
        name_b: str,
        amount: float,
        track: int,
        use_nrpn: bool = False,
    ) -> dict:
        """
        Interpolate between two saved patches and send the result.

        Args:
            name_a (str): Patch at amount 0.0.
            name_b (str): Patch at amount 1.0.
            amount (float): Position between them, 0.0 to 1.0.
            track (int): Digitone track / MIDI channel, 1-16.
            use_nrpn (bool): Send over 14-bit NRPN instead of 7-bit CC.

        Returns:
            dict: The interpolated values and the result of sending them.
        """
        try:
            a, b = store.load(name_a), store.load(name_b)
        except FileNotFoundError as e:
            return {"error": str(e)}
        blended = store.morph(a["sections"], b["sections"], amount)
        return {
            "morphed": {"from": name_a, "to": name_b, "amount": amount},
            "values": blended,
            "result": apply_sections(midi, track, blended, use_nrpn),
        }

    @mcp.tool()
    def mutate_patch(
        track: int,
        amount: float = 0.1,
        name: str | None = None,
        only: list[str] | None = None,
        seed: int | None = None,
        use_nrpn: bool = False,
    ) -> dict:
        """
        Apply random offsets around a patch and send the result.

        Use it to explore around a sound that is nearly right. Restricting
        `only` to a few parameters explores one dimension at a time, which is
        usually more useful than moving everything at once.

        Args:
            track (int): Digitone track / MIDI channel, 1-16.
            amount (float): Spread as a fraction of full range, 0.0 to 1.0.
                0.1 is roughly +/-12 MIDI units.
            name (str): Saved patch to mutate. Omit to mutate the track's
                current tracked state.
            only (list[str]): Restrict mutation to these parameter names.
            seed (int): Seed for a repeatable mutation.
            use_nrpn (bool): Send over 14-bit NRPN instead of 7-bit CC.

        Returns:
            dict: The mutated values and the result of sending them.
        """
        if name:
            try:
                base = store.load(name)["sections"]
            except FileNotFoundError as e:
                return {"error": str(e)}
        else:
            base = store.TRACK_STATE.get(track)
            if not base:
                return {
                    "error": f"nothing tracked for track {track}; set some "
                    "parameters first or pass a saved patch name"
                }

        mutated = store.mutate(base, amount, only, random.Random(seed))
        return {
            "mutated": {"base": name or f"track {track} state",
                        "amount": amount, "seed": seed, "only": only},
            "values": mutated,
            "result": apply_sections(midi, track, mutated, use_nrpn),
        }

    @mcp.tool()
    def clear_track_state(track: int | None = None) -> dict:
        """
        Forget the tracked parameter values for a track, or all tracks.

        Sends nothing to the hardware; this only resets what the server
        believes it has set.

        Args:
            track (int): Digitone track / MIDI channel 1-16, or omit for all.

        Returns:
            dict: What was cleared.
        """
        store.TRACK_STATE.clear(track)
        return {"cleared": track if track else "all tracks"}
