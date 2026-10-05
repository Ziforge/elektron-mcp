"""
Read and write Digitone II `.dn2pst` Sound presets.

A preset is a ZIP holding a plain-JSON manifest and a binary parameter
payload. Inside the payload, parameters are a contiguous array of 16-bit
words with the 7-bit value in the odd byte of each word. See
docs/preset-format.md for how that was established.

Writing works by templating: an existing preset downloaded from the device
supplies the header, and only the parameter words are overwritten. The header
is not understood, so it is never synthesised -- if it carries a checksum or
length field, templating keeps it valid where constructing one would not.
"""

import io
import json
import struct
import zipfile
import zlib
from pathlib import Path

# FM DRUM parameter order as stored in the payload. This follows the device's
# page layout, not CC numbering: fold precedes algo, ratio1 follows end1.
FM_DRUM_ORDER = (
    "tune", "stim", "sdep", "fold", "algo", "fdbk", "op_c", "op_ab",
    "dec1", "end1", "ratio1", "mod1", "dec2", "end2", "ratio2", "mod2",
    "hold", "tran", "base", "wdth", "ndec", "nlev", "tlev", "dec",
    "lev", "ph_c", "nrst", "nrm", "nhld", "gran",
)

BLOCK_START = 85
STRIDE = 2

# The device validates payload integrity and rejects a mismatch with
# "Content hash mismatch". The hash is CRC-32 seeded 0xffffffff over the
# payload from CRC_START up to the footer, stored big-endian 12 bytes from
# the end. Verified against six presets taken off the device.
CRC_START = 32
CRC_FIELD_FROM_END = 12
FOOTER_MAGIC = bytes.fromhex("aaa1daaa")

MACHINE_LAYOUTS = {"fm_drum": (BLOCK_START, STRIDE, FM_DRUM_ORDER)}

# The offsets above were derived from one calibration preset and decode it
# exactly. They are NOT known to generalise: payload length varies between
# presets (247 to 334 bytes observed) and the device re-serialises a preset
# on save, returning 266 bytes for a 271-byte upload. That means the payload
# is probably tagged or variable-length rather than a flat array, so an
# absolute offset is only trustworthy for a payload of the calibrated length.
CALIBRATED_PAYLOAD_LEN = 271


class PresetError(RuntimeError):
    """Raised when a preset cannot be read or written."""


def offsets(machine: str = "fm_drum") -> dict[str, int]:
    """Byte offset of each parameter's value within the payload."""
    if machine not in MACHINE_LAYOUTS:
        raise PresetError(
            f"no payload layout known for {machine!r}; only "
            f"{sorted(MACHINE_LAYOUTS)} have been calibrated"
        )
    start, stride, order = MACHINE_LAYOUTS[machine]
    return {name: start + i * stride for i, name in enumerate(order)}


def read(path: str | Path, machine: str = "fm_drum") -> dict:
    """Read a preset: manifest, parameter values and the raw payload."""
    path = Path(path)
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if "manifest.json" not in names:
                raise PresetError(f"{path.name} has no manifest.json")
            manifest = json.loads(z.read("manifest.json"))
            payload_name = manifest.get("Payload")
            if payload_name not in names:
                raise PresetError(
                    f"manifest names payload {payload_name!r}, not in archive"
                )
            payload = z.read(payload_name)
    except zipfile.BadZipFile as e:
        raise PresetError(f"{path.name} is not a ZIP archive: {e}") from e

    params = {}
    for name, off in offsets(machine).items():
        if off < len(payload):
            params[name] = payload[off]

    return {
        "name": payload_name,
        "manifest": manifest,
        "file_type": manifest.get("FileType"),
        "firmware": manifest.get("FirmwareVersion"),
        "tags": manifest.get("MetaInfo", {}).get("Tags", []),
        "payload": payload,
        "parameters": params,
    }


def layout_is_trusted(payload: bytes) -> bool:
    """Whether the known offsets can be trusted for this payload."""
    return len(payload) == CALIBRATED_PAYLOAD_LEN


def apply_parameters(payload: bytes, values: dict[str, int],
                     machine: str = "fm_drum",
                     require_trusted: bool = True) -> tuple[bytes, list[str]]:
    """Overwrite parameter values in a payload. Returns (payload, unknown).

    Refuses a payload whose length differs from the calibrated one, since the
    offsets are not known to generalise and writing to the wrong ones
    produces a preset that uploads cleanly and sounds like nothing intended.
    """
    if require_trusted and not layout_is_trusted(payload):
        raise PresetError(
            f"payload is {len(payload)} bytes but the parameter offsets were "
            f"calibrated on {CALIBRATED_PAYLOAD_LEN}; refusing to write to "
            "offsets that may not apply. Recalibrate for this payload length."
        )
    buf = bytearray(payload)
    known = offsets(machine)
    unknown = []
    for name, value in values.items():
        off = known.get(name)
        if off is None:
            unknown.append(name)
            continue
        if off >= len(buf):
            unknown.append(name)
            continue
        buf[off] = max(0, min(127, int(value)))
    return bytes(buf), unknown


def content_crc(payload: bytes) -> int:
    """The payload's content hash, as the device computes it."""
    body = payload[CRC_START:len(payload) - CRC_FIELD_FROM_END]
    return zlib.crc32(body, 0xFFFFFFFF) & 0xFFFFFFFF


def stored_crc(payload: bytes) -> int:
    """The hash currently recorded in the payload's footer."""
    return struct.unpack_from(">I", payload,
                              len(payload) - CRC_FIELD_FROM_END)[0]


def reseal(payload: bytes) -> bytes:
    """Recompute the content hash after editing a payload.

    Without this the device refuses the upload: editing parameter bytes
    invalidates the stored hash, and it reports "Content hash mismatch".
    """
    buf = bytearray(payload)
    struct.pack_into(">I", buf, len(buf) - CRC_FIELD_FROM_END,
                     content_crc(bytes(buf)))
    return bytes(buf)


def verify(payload: bytes) -> bool:
    """Whether the stored hash matches the content."""
    return stored_crc(payload) == content_crc(payload)


def write(path: str | Path, payload: bytes, name: str,
          tags: list[str] | None = None,
          firmware: str = "1.11", product_type: str = "43") -> str:
    """Write a `.dn2pst`, reproducing the device's archive layout.

    The archive stores the payload under an entry named after the preset, and
    the manifest points at it by that name.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "FormatVersion": "1.0",
        "ProductType": [product_type],
        "Payload": name,
        "FileType": "Sound",
        "FirmwareVersion": firmware,
    }
    if tags:
        manifest["MetaInfo"] = {"Tags": list(tags)}

    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
        z.writestr(name, payload)
    path.write_bytes(raw.getvalue())
    return str(path)


def rename_in_payload(payload: bytes, old: str, new: str) -> bytes:
    """Replace the preset name embedded in the payload.

    The name appears in the payload as well as in the manifest, and at an
    offset that differs between presets, so it is located by search rather
    than assumed. The replacement is padded or truncated to the original
    length, since changing the payload length would almost certainly
    invalidate it. Not verified against the device -- the device may well
    take its displayed name from the manifest alone.
    """
    encoded_old = old.encode("ascii", "ignore")
    at = payload.find(encoded_old)
    if at < 0:
        return payload
    fitted = new.encode("ascii", "ignore")[: len(encoded_old)]
    fitted = fitted + b"\x00" * (len(encoded_old) - len(fitted))
    return payload[:at] + fitted + payload[at + len(encoded_old):]


def build_from_template(template: str | Path, values: dict[str, int],
                        name: str, dest: str | Path,
                        tags: list[str] | None = None,
                        machine: str = "fm_drum") -> dict:
    """Make a new preset from an existing one plus parameter values."""
    source = read(template, machine)
    payload, unknown = apply_parameters(source["payload"], values, machine)
    payload = rename_in_payload(payload, source["name"], name)
    payload = reseal(payload)
    written = write(dest, payload, name, tags or source["tags"],
                    source["firmware"] or "1.11")
    return {
        "file": written,
        "name": name,
        "template": str(template),
        "parameters_written": {k: v for k, v in values.items()
                               if k not in unknown},
        "unknown_parameters": unknown,
    }
