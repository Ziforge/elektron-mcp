"""Elektron SysEx framing and codec."""

from elektron_mcp.preset import sysex


def test_codec_round_trips_arbitrary_bytes():
    for payload in (b"", b"\x00", bytes(range(256)), b"\xff" * 20,
                    b"\x00\x20\x3c\x10\x00\x01"):
        assert sysex.decode_7bit(sysex.encode_7bit(payload))[:len(payload)] \
            == payload


def test_encoded_output_is_midi_safe():
    """Every byte after a group's leading high-bit byte must be 7-bit."""
    encoded = sysex.encode_7bit(bytes(range(256)))
    for start in range(0, len(encoded), 8):
        for byte in encoded[start + 1:start + 8]:
            assert byte < 0x80


def test_ping_matches_the_bytes_the_reference_client_sends():
    """Captured from a known-good client: the PING body encodes to
    00 00 00 00 00 01 after the header."""
    assert sysex.build(sysex.PING) == list(sysex.HEADER) + [0, 0, 0, 0, 0, 1]


def test_path_is_nul_terminated_in_the_payload():
    body = sysex.decode_7bit(
        bytes(sysex.build(b"\x19\x00", "/B/175", b"\x0d")[len(sysex.HEADER):]))
    assert body.startswith(b"\x00\x00\x00\x00\x19\x00")
    assert b"/B/175\x00" in body


def test_parse_reply_rejects_messages_from_other_makers():
    assert sysex.parse_reply(bytes([0x7E, 0x00, 0x06, 0x02])) is None
    assert sysex.parse_reply(b"") is None


def test_parse_reply_decodes_our_own_framing():
    body = b"\x00\x00\x00\x00\x01\x80\x7f"
    raw = bytes(sysex.HEADER) + sysex.encode_7bit(body)
    assert sysex.parse_reply(raw)[:len(body)] == body
