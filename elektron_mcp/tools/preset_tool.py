"""
Preset and project transfer tools.

These make saving automatable: a preset file written into a slot requires no
interaction with the device, unlike committing live parameter state, which
has no MIDI equivalent at all.

Every tool hands the MIDI port to Elektroid and takes it back afterwards,
because only one process can hold it.
"""

import contextlib
from pathlib import Path

from elektron_mcp.patches.store import TRACK_STATE
from elektron_mcp.preset import elektroid, sound

DEFAULT_BACKUP_DIR = Path.home() / ".elektron-mcp" / "device-backups"
PRESET_FS = "preset-takt-ii"

# An FM DRUM preset downloaded from the device, used as a header template.
# The header is not understood, so it is templated rather than synthesised:
# if it carries a checksum or length field, reusing a real one keeps it valid.
DEFAULT_TEMPLATE = (Path.home() / ".elektron-mcp" / "calibration" /
                    "download" / "CALIB1.dn2pst")
PROJECT_FS = "project"


@contextlib.contextmanager
def _port_handover(midi):
    """Release the server's MIDI port for the duration, then restore it."""
    was_connected = bool(midi.connected)
    port = midi.output_port_name
    if was_connected:
        midi.disconnect()
    try:
        yield
    finally:
        if was_connected:
            if port:
                midi.connect(port)
            else:
                midi.auto_connect()


def register_preset_tools(mcp, midi):
    """Register device storage tools with the MCP server."""

    @mcp.tool()
    def transfer_readiness() -> dict:
        """
        Check whether preset and project transfer can work.

        Reports whether elektroid-cli is present and whether its device table
        is installed. A missing device table is the subtle failure: the
        handshake still succeeds and the instrument is reported as a generic
        "MIDI device" with no preset or project filesystems, which looks
        exactly like a device that is not responding.

        Returns:
            dict: What was found, and what to fix if anything is missing.
        """
        state = elektroid.readiness()
        if not state["cli_found"]:
            return state
        try:
            with _port_handover(midi):
                index = elektroid.find_device("Digitone")
                state["device_index"] = index
                state["device"] = elektroid.device_info(index)
        except elektroid.ElektroidError as e:
            state["error"] = str(e)
        return state

    @mcp.tool()
    def list_device_presets(bank: str = "A") -> dict:
        """
        List the presets stored in a bank on the device.

        Slow: one SysEx round trip per slot, so a bank can take minutes.

        Args:
            bank (str): Bank letter, A to H.

        Returns:
            dict: Raw listing lines, with names and tags.
        """
        if not (len(bank) == 1 and bank.upper() in "ABCDEFGH"):
            return {"error": f"bank must be a single letter A-H, got {bank!r}"}
        try:
            with _port_handover(midi):
                index = elektroid.find_device("Digitone")
                out = elektroid.ls(index, PRESET_FS, f"/{bank.upper()}")
        except elektroid.ElektroidError as e:
            return {"error": str(e)}
        lines = [ln for ln in out.splitlines() if ln.strip()]
        return {"bank": bank.upper(), "entries": lines, "count": len(lines)}

    @mcp.tool()
    def list_device_projects() -> dict:
        """
        List the projects stored on the device.

        Returns:
            dict: Raw listing lines, one per project slot.
        """
        try:
            with _port_handover(midi):
                index = elektroid.find_device("Digitone")
                out = elektroid.ls(index, PROJECT_FS, "/")
        except elektroid.ElektroidError as e:
            return {"error": str(e)}
        lines = [ln for ln in out.splitlines() if ln.strip()]
        return {"entries": lines, "count": len(lines)}

    @mcp.tool()
    def download_preset(slot: str, dest: str | None = None) -> dict:
        """
        Download a preset from the device.

        A preset is only a few hundred bytes, so this is quick. Downloading a
        preset whose parameter values are already known is how the byte layout
        gets decoded, which is what makes writing presets possible later.

        Args:
            slot (str): Path on the device, e.g. 'A/001'.
            dest (str): Directory to write into. Defaults to the backup
                directory under ~/.elektron-mcp.

        Returns:
            dict: Where it was written.
        """
        target = Path(dest) if dest else DEFAULT_BACKUP_DIR / "presets"
        try:
            with _port_handover(midi):
                index = elektroid.find_device("Digitone")
                out = elektroid.download(index, PRESET_FS, f"/{slot.lstrip('/')}",
                                         str(target))
        except elektroid.ElektroidError as e:
            return {"error": str(e)}
        files = sorted(str(p) for p in target.glob("*") if p.is_file())
        return {"slot": slot, "directory": str(target),
                "files": files[-5:], "output": out.strip() or None}

    @mcp.tool()
    def upload_preset(local_file: str, slot: str) -> dict:
        """
        Upload a preset file into a slot on the device.

        This is the write path that makes saving automatable: no button
        presses on the device are involved. It overwrites the target slot, so
        prefer an empty one.

        Args:
            local_file (str): Path to the preset file to send.
            slot (str): Destination on the device, e.g. 'A/015'.

        Returns:
            dict: What was sent where.
        """
        if not Path(local_file).is_file():
            return {"error": f"no such file: {local_file}"}
        try:
            with _port_handover(midi):
                index = elektroid.find_device("Digitone")
                out = elektroid.upload(index, PRESET_FS, local_file,
                                       f"/{slot.lstrip('/')}")
        except elektroid.ElektroidError as e:
            return {"error": str(e)}
        return {"uploaded": local_file, "slot": slot,
                "output": out.strip() or None}

    @mcp.tool()
    def copy_device_preset(source_slot: str, dest_slot: str) -> dict:
        """
        Copy a preset from one slot to another, on the device.

        Args:
            source_slot (str): e.g. 'A/001'.
            dest_slot (str): e.g. 'A/016'. Overwritten if occupied.

        Returns:
            dict: What was copied.
        """
        try:
            with _port_handover(midi):
                index = elektroid.find_device("Digitone")
                out = elektroid.copy(index, PRESET_FS,
                                     f"/{source_slot.lstrip('/')}",
                                     f"/{dest_slot.lstrip('/')}")
        except elektroid.ElektroidError as e:
            return {"error": str(e)}
        return {"copied": source_slot, "to": dest_slot,
                "output": out.strip() or None}

    @mcp.tool()
    def export_preset_file(
        name: str,
        track: int = 14,
        dest: str | None = None,
        tags: list[str] | None = None,
        template: str | None = None,
    ) -> dict:
        """
        Build a preset file from a track's current parameter values.

        Writes a .dn2pst locally without touching the device, so the result
        can be inspected or version-controlled before being uploaded.

        Values come from what this server has sent to the track, so set the
        parameters first. Only FM DRUM is calibrated; other machines store
        their parameters in a different order and are not supported yet.

        Args:
            name (str): Preset name, as it will appear on the device.
            track (int): Track whose tracked values to use, 1-16.
            dest (str): Output path. Defaults to the backup directory.
            tags (list[str]): Optional tags, e.g. ['PERCUSSION'].
            template (str): Preset file to take the header from.

        Returns:
            dict: Where it was written and which parameters it carries.
        """
        state = TRACK_STATE.get(track)
        values = state.get("fm_drum", {})
        if not values:
            return {
                "error": f"no fm_drum values tracked for track {track}; set "
                "parameters first, or recall a patch"
            }

        tpl = Path(template) if template else DEFAULT_TEMPLATE
        if not tpl.is_file():
            return {
                "error": f"no template preset at {tpl}. Download an FM DRUM "
                "preset from the device first -- the header is templated "
                "rather than synthesised."
            }

        target = Path(dest) if dest else (
            DEFAULT_BACKUP_DIR / "built" / f"{name}.dn2pst")
        try:
            result = sound.build_from_template(tpl, values, name, target, tags)
        except sound.PresetError as e:
            return {"error": str(e)}
        result["note"] = (
            "built locally; upload_preset sends it to the device. The header "
            "is copied from the template and has not been decoded."
        )
        return result

    @mcp.tool()
    def save_current_as_preset(
        name: str,
        slot: str,
        track: int = 14,
        tags: list[str] | None = None,
        template: str | None = None,
    ) -> dict:
        """
        Save a track's current sound to a preset slot on the device.

        Builds a preset file from the tracked parameter values and uploads
        it, with no interaction with the device. This is what makes saving
        automatable: committing live parameter state has no MIDI equivalent,
        but writing a preset file to a slot does.

        Overwrites the target slot, so prefer an empty one.

        Only FM DRUM is calibrated. The templated header has not been
        decoded, so verify the result sounds right after saving.

        Args:
            name (str): Preset name as it will appear on the device.
            slot (str): Destination slot, e.g. 'B/175'.
            track (int): Track whose values to save, 1-16.
            tags (list[str]): Optional tags.
            template (str): Preset file to take the header from.

        Returns:
            dict: What was built and the result of uploading it.
        """
        built = export_preset_file(name, track, None, tags, template)
        if "error" in built:
            return built
        try:
            with _port_handover(midi):
                index = elektroid.find_device("Digitone")
                out = elektroid.upload(index, PRESET_FS, built["file"],
                                       f"/{slot.lstrip('/')}")
        except elektroid.ElektroidError as e:
            return {"error": str(e), "built": built}
        return {
            "saved": name, "slot": slot, "built": built,
            "output": out.strip() or None,
            "note": "verify on the device: the preset header is templated "
                    "and has not been decoded.",
        }

    @mcp.tool()
    def backup_device_project(slot: str = "002",
                              dest: str | None = None) -> dict:
        """
        Download a project from the device as a backup.

        Projects are large and transfer over SysEx, so this takes a long
        time. Worth doing before any experiment that writes to the device.

        Args:
            slot (str): Project slot, e.g. '002'.
            dest (str): Directory to write into.

        Returns:
            dict: Where it was written.
        """
        target = Path(dest) if dest else DEFAULT_BACKUP_DIR / "projects"
        try:
            with _port_handover(midi):
                index = elektroid.find_device("Digitone")
                out = elektroid.download(index, PROJECT_FS,
                                         f"/{slot.lstrip('/')}", str(target))
        except elektroid.ElektroidError as e:
            return {"error": str(e)}
        files = sorted(str(p) for p in target.glob("*") if p.is_file())
        return {"project_slot": slot, "directory": str(target),
                "files": files[-5:], "output": out.strip() or None}
