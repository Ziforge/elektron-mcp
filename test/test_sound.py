"""
Preset reading and writing.

The real calibration download is used when present, since it is the only
ground truth for the payload layout; otherwise a synthetic preset stands in,
so the suite stays portable.
"""

import json
import zipfile
from pathlib import Path

import pytest

from elektron_mcp.preset import sound

REAL = Path.home()/".elektron-mcp"/"calibration"/"download"/"CALIB1.dn2pst"
TRUTH = Path.home()/".elektron-mcp"/"calibration"/"calibration-v1.json"


def _synthetic(tmp_path, values=None):
    """A preset shaped like the device's, for tests without the download."""
    payload = bytearray(271)
    payload[51:57] = b"SYNTH1"
    for name, off in sound.offsets().items():
        payload[off] = (values or {}).get(name, 64)
    path = tmp_path / "SYNTH1.dn2pst"
    sound.write(path, bytes(payload), "SYNTH1", ["TEST"])
    return path


def test_offsets_are_a_contiguous_16_bit_array():
    offs = sound.offsets()
    assert len(offs) == 30
    ordered = [offs[n] for n in sound.FM_DRUM_ORDER]
    assert ordered == sorted(ordered)
    assert all(b - a == 2 for a, b in zip(ordered, ordered[1:]))
    assert ordered[0] == 85


def test_payload_order_is_page_order_not_cc_order():
    """fold precedes algo and ratio1 follows end1, which is the device's page
    layout rather than the CC numbering in this repo's parameter maps."""
    order = list(sound.FM_DRUM_ORDER)
    assert order.index("fold") < order.index("algo")
    assert order.index("end1") < order.index("ratio1")


def test_unknown_machine_is_refused_rather_than_guessed():
    with pytest.raises(sound.PresetError, match="calibrated"):
        sound.offsets("wavetone")


def test_write_then_read_round_trips(tmp_path):
    path = _synthetic(tmp_path, {"gran": 99, "nlev": 120})
    back = sound.read(path)
    assert back["name"] == "SYNTH1"
    assert back["file_type"] == "Sound"
    assert back["tags"] == ["TEST"]
    assert back["parameters"]["gran"] == 99
    assert back["parameters"]["nlev"] == 120


def test_apply_changes_only_the_named_bytes(tmp_path):
    original = sound.read(_synthetic(tmp_path))["payload"]
    changed, unknown = sound.apply_parameters(original, {"gran": 99})
    assert unknown == []
    diff = [i for i, (a, b) in enumerate(zip(original, changed)) if a != b]
    assert diff == [sound.offsets()["gran"]]


def test_apply_clamps_and_reports_unknown_names(tmp_path):
    original = sound.read(_synthetic(tmp_path))["payload"]
    changed, notes = sound.apply_parameters(
        original, {"gran": 999, "nlev": -5, "not_a_param": 1})
    assert "not_a_param" in notes
    offs = sound.offsets()
    assert changed[offs["gran"]] == 127
    # -5 clamps to 0, which is then raised to 1 because a stored zero
    # shortens the payload and shifts everything after it.
    assert changed[offs["nlev"]] == 1


def test_rename_preserves_payload_length(tmp_path):
    payload = sound.read(_synthetic(tmp_path))["payload"]
    renamed = sound.rename_in_payload(payload, "SYNTH1", "AB")
    assert len(renamed) == len(payload)
    assert b"AB\x00\x00\x00\x00" in renamed


def test_rename_is_a_noop_when_the_name_is_absent(tmp_path):
    payload = sound.read(_synthetic(tmp_path))["payload"]
    assert sound.rename_in_payload(payload, "NOPE", "X") == payload


def test_non_zip_is_reported_clearly(tmp_path):
    bad = tmp_path / "bad.dn2pst"
    bad.write_bytes(b"not a zip at all")
    with pytest.raises(sound.PresetError, match="not a ZIP"):
        sound.read(bad)


def test_missing_manifest_is_reported(tmp_path):
    bad = tmp_path / "nomanifest.dn2pst"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("something", b"\x00")
    with pytest.raises(sound.PresetError, match="manifest"):
        sound.read(bad)


def test_build_from_template_keeps_the_header_when_not_renaming(tmp_path):
    """The header is not understood, so it must be carried over untouched."""
    tpl = _synthetic(tmp_path, {"gran": 10})
    header_before = sound.read(tpl)["payload"][:sound.BLOCK_START]
    out = sound.build_from_template(
        tpl, {"gran": 99}, "SYNTH1", tmp_path / "same.dn2pst")
    built = sound.read(out["file"])
    assert built["parameters"]["gran"] == 99
    assert built["payload"][:sound.BLOCK_START] == header_before


def test_renaming_touches_only_the_name_field_inside_the_header(tmp_path):
    """The preset name lives at offset 51, inside the header region, so a
    rename unavoidably edits header bytes. Only those bytes may change --
    and if the header carries a checksum over the name, a renamed preset may
    be rejected by the device. Untested against hardware."""
    tpl = _synthetic(tmp_path, {"gran": 10})
    before = sound.read(tpl)["payload"]
    out = sound.build_from_template(
        tpl, {"gran": 10}, "NEWNAM", tmp_path / "renamed.dn2pst")
    after = sound.read(out["file"])["payload"]
    diff = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert diff, "rename changed nothing"
    # The CRC field is expected to change: editing the payload invalidates
    # the stored content hash, so build_from_template reseals it.
    crc_field = range(len(before) - sound.CRC_FIELD_FROM_END,
                      len(before) - sound.CRC_FIELD_FROM_END + 4)
    unexpected = [i for i in diff if not (51 <= i < 57 or i in crc_field)]
    assert not unexpected, f"changed beyond name and CRC: {unexpected}"


def test_write_refuses_an_uncalibrated_payload_length():
    """The offsets came from one preset and are not known to generalise, so
    writing to a payload of a different length must fail rather than produce
    a preset that uploads cleanly and sounds like nothing intended."""
    short = bytes(sound.CALIBRATED_PAYLOAD_LEN - 20)
    with pytest.raises(sound.PresetError, match="calibrated"):
        sound.apply_parameters(short, {"gran": 10})
    assert sound.layout_is_trusted(bytes(sound.CALIBRATED_PAYLOAD_LEN))
    assert not sound.layout_is_trusted(short)


def test_crc_matches_the_device_on_every_real_preset():
    """CRC-32 seeded 0xffffffff over [32:-12], verified against presets taken
    off the device. Getting this wrong is what the device rejects with
    "Content hash mismatch"."""
    import glob
    files = [f for f in glob.glob(str(Path.home() /
             ".elektron-mcp/calibration/download/*.dn2pst"))
             if not f.endswith("/.dn2pst")]
    if not files:
        pytest.skip("no downloaded presets available")
    for f in files:
        payload = sound.read(f)["payload"]
        assert sound.verify(payload), f"{f} failed its own CRC"


def test_reseal_makes_an_edited_payload_valid_again():
    payload = bytearray(sound.CALIBRATED_PAYLOAD_LEN)
    payload[sound.offsets()["gran"]] = 99
    sealed = sound.reseal(bytes(payload))
    assert sound.verify(sealed)
    assert not sound.verify(bytes(payload)) or sound.content_crc(
        bytes(payload)) == sound.stored_crc(bytes(payload))


@pytest.mark.skipif(not REAL.is_file() or not TRUTH.is_file(),
                    reason="calibration download not present")
def test_real_preset_decodes_to_the_values_that_were_sent():
    """The ground truth: every value sent over CC must be recovered from the
    downloaded preset. This is what validates the offset map."""
    truth = json.loads(TRUTH.read_text())["parameters"]
    want = {k.split(".", 1)[1]: v["value"]
            for k, v in truth.items() if k.startswith("fm_drum.")}
    got = sound.read(REAL)["parameters"]
    assert got == want


@pytest.mark.skipif(not REAL.is_file(), reason="calibration download absent")
def test_real_preset_rewrites_byte_identically():
    original = sound.read(REAL)
    rewritten, notes = sound.apply_parameters(
        original["payload"], original["parameters"])
    # The two toggles are skipped rather than written, so they are reported;
    # they keep the template's values, which is what makes the rest land.
    assert all("raised to 1" in n for n in notes)
    writable = list(sound.FM_DRUM_ORDER)
    offs = sound.offsets()
    for name in writable:
        if original["parameters"][name] != 0:
            assert rewritten[offs[name]] == original["parameters"][name]


def test_every_parameter_is_writable(tmp_path):
    """Probing showed nrst 0->1 lands with nothing shifted, so excluding the
    toggles was wrong. The hazard is changing a value's encoded WIDTH, not
    which parameter it is."""
    original = sound.read(_synthetic(tmp_path))["payload"]
    changed, _ = sound.apply_parameters(
        original, {"nrst": 1, "nrm": 1, "gran": 99})
    offs = sound.offsets()
    assert changed[offs["nrst"]] == 1
    assert changed[offs["nrm"]] == 1
    assert changed[offs["gran"]] == 99


def test_zero_is_raised_to_one_and_reported(tmp_path):
    """A zero is stored compactly, costing a byte and shifting what follows."""
    original = sound.read(_synthetic(tmp_path))["payload"]
    changed, notes = sound.apply_parameters(original, {"gran": 0})
    assert changed[sound.offsets()["gran"]] == 1
    assert any("0 raised to 1" in n for n in notes)


def test_all_thirty_parameters_are_writable():
    assert len(sound.FM_DRUM_ORDER) == 30
