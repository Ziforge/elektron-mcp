"""
Thin wrapper around elektroid-cli.

Elektroid implements Elektron's proprietary SysEx transfer protocol, which is
how presets and projects move on and off the device. It is GPL-3.0 while this
project is MIT, so it is driven as a subprocess rather than linked or ported:
no licence entanglement, and no reimplementation of its 7-bit payload encoder.

Only one process can hold the instrument's MIDI port, so every call here
releases the server's port and restores it afterwards. Without that the two
simply fight and Elektroid times out.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

DEFAULT_PATHS = (
    "/Volumes/MAC_M3_Store/Dev/elektroid/src/elektroid-cli",
    "/opt/homebrew/bin/elektroid-cli",
    "/usr/local/bin/elektroid-cli",
)

# Elektroid needs its device table to recognise the instrument. Without it the
# handshake succeeds and it still falls back to a generic connector, reporting
# the device as an unremarkable "MIDI device" -- which reads exactly like a
# silent instrument and is easy to misdiagnose.
DEVICES_JSON = Path.home() / ".config/elektroid/elektron/devices.json"


class ElektroidError(RuntimeError):
    """Raised when the CLI is missing, misconfigured, or fails."""


def cli_path() -> str | None:
    """Locate elektroid-cli: ELEKTROID_CLI, then PATH, then known builds."""
    env = os.environ.get("ELEKTROID_CLI")
    if env and os.access(env, os.X_OK):
        return env
    found = shutil.which("elektroid-cli")
    if found:
        return found
    for candidate in DEFAULT_PATHS:
        if os.access(candidate, os.X_OK):
            return candidate
    return None


def readiness() -> dict:
    """Report whether transfers can work, and what is missing if not."""
    path = cli_path()
    return {
        "cli": path,
        "cli_found": path is not None,
        "devices_json": str(DEVICES_JSON),
        "devices_json_installed": DEVICES_JSON.is_file(),
        "note": None if (path and DEVICES_JSON.is_file()) else (
            "install elektroid-cli and copy res/elektron/devices.json to "
            f"{DEVICES_JSON}; without the device table Elektroid reports the "
            "instrument as a generic MIDI device"
        ),
    }


def _run(args: list[str], timeout: float) -> str:
    path = cli_path()
    if path is None:
        raise ElektroidError("elektroid-cli not found; set ELEKTROID_CLI")
    try:
        done = subprocess.run([path, *args], capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise ElektroidError(
            f"elektroid-cli timed out after {timeout:.0f}s: {' '.join(args)}"
        ) from e
    if done.returncode != 0:
        raise ElektroidError(
            (done.stderr or done.stdout or "unknown error").strip()
        )
    return done.stdout


def list_devices(timeout: float = 30) -> list[dict]:
    """Devices Elektroid can see, as (index, id, name)."""
    out = []
    for line in _run(["ld"], timeout).splitlines():
        m = re.match(r"\s*(\d+):\s*id:\s*(.*?);\s*name:\s*(.*?)\s*$", line)
        if m:
            out.append({"index": int(m.group(1)), "id": m.group(2),
                        "name": m.group(3)})
    return out


def find_device(match: str = "Digitone", timeout: float = 30) -> int:
    """Resolve a device index by name. Indices are not stable across runs."""
    devices = list_devices(timeout)
    for d in devices:
        if match.lower() in d["name"].lower():
            return d["index"]
    raise ElektroidError(
        f"no device matching {match!r}; saw {[d['name'] for d in devices]}"
    )


def device_info(index: int, timeout: float = 60) -> dict:
    """Parse `info` output, including the connector actually in use."""
    info = {}
    for line in _run(["info", str(index)], timeout).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            info[k.strip().lower().replace(" ", "_")] = v.strip()
    if info.get("connector") == "default":
        info["warning"] = (
            "Elektroid fell back to its generic connector, so preset and "
            "project filesystems are unavailable. The usual cause is a "
            "missing devices.json rather than a device problem."
        )
    return info


def ls(index: int, filesystem: str, path: str = "/",
       timeout: float = 600) -> str:
    """List a filesystem. Slow: one SysEx round trip per slot."""
    return _run([f"elektron:{filesystem}:ls", f"{index}:{path}"], timeout)


def download(index: int, filesystem: str, path: str, dest: str,
             timeout: float = 1800) -> str:
    """Download a preset or project into `dest`."""
    Path(dest).mkdir(parents=True, exist_ok=True)
    return _run([f"elektron:{filesystem}:dl", f"{index}:{path}", dest],
                timeout)


def upload(index: int, filesystem: str, local: str, path: str,
           timeout: float = 1800) -> str:
    """Upload a preset or project file to a slot.

    This is the write path that makes saving automatable: a preset file put
    into a slot needs no interaction with the device.
    """
    if not Path(local).is_file():
        raise ElektroidError(f"no such file: {local}")
    return _run([f"elektron:{filesystem}:ul", local, f"{index}:{path}"],
                timeout)


def copy(index: int, filesystem: str, src: str, dst: str,
         timeout: float = 600) -> str:
    """Copy a slot to another slot, on the device."""
    return _run([f"elektron:{filesystem}:cp", f"{index}:{src}",
                 f"{index}:{dst}"], timeout)
