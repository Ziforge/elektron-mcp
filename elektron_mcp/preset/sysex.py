"""
Elektron SysEx framing and 7-bit payload codec.

Written so the server is not limited to the commands elektroid-cli exposes.
Implemented from the protocol's observable behaviour and verified against the
hardware: a PING returns the device's own name.

Framing is `F0 00 20 3C 10 00` + encoded payload + `F7`, where the payload is
four zero bytes, an opcode, an optional NUL-terminated cp1252 path, and any
trailing arguments.

The codec is the usual MIDI problem of moving 8-bit data over a 7-bit
channel: each group of seven source bytes becomes eight, led by a byte
carrying their high bits.
"""

MANUFACTURER = (0x00, 0x20, 0x3C)
HEADER = (0x00, 0x20, 0x3C, 0x10, 0x00)

PING = b"\x01"
SOFTWARE_VERSION = b"\x02"
DEVICE_UID = b"\x03"
STORAGE_INFO = b"\x05"


def encode_7bit(data: bytes) -> bytes:
    """Pack 8-bit data for a 7-bit channel."""
    out = bytearray()
    for start in range(0, len(data), 7):
        chunk = data[start:start + 7]
        high = 0
        for i in range(7):
            high <<= 1
            if i < len(chunk) and chunk[i] & 0x80:
                high |= 1
        out.append(high)
        out.extend(b & 0x7F for b in chunk)
    return bytes(out)


def decode_7bit(data: bytes) -> bytes:
    """Unpack what encode_7bit produced."""
    out = bytearray()
    for start in range(0, len(data), 8):
        group = data[start:start + 8]
        if not group:
            break
        high = group[0]
        for i, byte in enumerate(group[1:]):
            out.append(byte | (0x80 if high & (0x40 >> i) else 0))
    return bytes(out)


def build(opcode: bytes, path: str | None = None, tail: bytes = b"") -> list[int]:
    """Message body for mido, which supplies F0 and F7 itself."""
    body = bytearray(b"\x00\x00\x00\x00") + opcode
    if path is not None:
        body += path.encode("cp1252", "replace") + b"\x00"
    body += tail
    return list(HEADER) + list(encode_7bit(bytes(body)))


def parse_reply(data: bytes) -> bytes | None:
    """Strip the header from a reply and decode it. None if not ours."""
    if len(data) < len(HEADER) or tuple(data[:len(HEADER)]) != HEADER:
        return None
    return decode_7bit(bytes(data[len(HEADER):]))
