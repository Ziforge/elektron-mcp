"""
Tests for the sound-design loop: analysis, capture IO, patch state, display
scaling, NRPN and MIDI learn.
"""

import asyncio

import mido
import numpy as np
import pytest

from elektron_mcp.audio import analysis, capture
from elektron_mcp.digitone.data.sections import SECTIONS
from elektron_mcp.patches import store
from elektron_mcp.tools import section_tool
from elektron_mcp.tools.learn_tool import _summarise

SR = 48000


class FakeMidi:
    """Records what would have been sent, so tests need no hardware."""

    def __init__(self, cc_ok=True, nrpn_ok=True):
        self.ccs, self.nrpns = [], []
        self.cc_ok, self.nrpn_ok = cc_ok, nrpn_ok

    def send_cc(self, channel, cc, value):
        self.ccs.append((channel, cc, value))
        return self.cc_ok

    def send_nrpn(self, channel, msb, lsb, value):
        self.nrpns.append((channel, msb, lsb, value))
        return self.nrpn_ok


@pytest.fixture
def rattle():
    """Dense high-band noise bursts -- a shaker, not a pitched bell."""
    rng = np.random.default_rng(0)
    x = np.zeros(SR // 2)
    for t in range(0, len(x) - 2000, 900):
        x[t:t + 2000] += rng.normal(0, 1, 2000) * np.exp(-np.linspace(0, 8, 2000))
    spec = np.fft.rfft(x)
    spec[: int(len(spec) * 0.08)] = 0
    x = np.fft.irfft(spec, n=len(x))
    return x / np.max(np.abs(x))


@pytest.fixture
def ping():
    t = np.arange(SR // 2) / SR
    return np.sin(2 * np.pi * 3000 * t) * np.exp(-t * 12)


def test_flatness_separates_noise_from_tone(rattle, ping):
    """The descriptor that tells a rattle from a bell has to actually do so."""
    assert analysis.describe(rattle, SR)["spectral_flatness"] > 0.2
    assert analysis.describe(ping, SR)["spectral_flatness"] < 0.05


def test_onset_count_separates_a_shake_from_one_hit(rattle, ping):
    assert analysis.describe(rattle, SR)["onsets"] > 5
    assert analysis.describe(ping, SR)["onsets"] == 1


def test_band_energy_locates_a_high_sound(rattle):
    d = analysis.describe(rattle, SR)
    assert d["energy_above_2k"] > 0.8
    assert d["energy_below_1k"] < 0.05


def test_silence_is_reported_not_described():
    d = analysis.describe(np.zeros(SR // 10), SR)
    assert d["silent"] is True
    assert "spectral_centroid_hz" not in d


def test_decay_time_tracks_the_envelope():
    t = np.arange(SR) / SR
    fast = np.sin(2 * np.pi * 440 * t) * np.exp(-t * 40)
    slow = np.sin(2 * np.pi * 440 * t) * np.exp(-t * 4)
    assert analysis.decay_time_ms(fast, SR) < analysis.decay_time_ms(slow, SR)


def test_mstft_distance_is_zero_against_self_and_positive_otherwise(rattle, ping):
    assert analysis.mstft_distance(rattle, rattle, SR)["distance"] == 0.0
    assert analysis.mstft_distance(rattle, ping, SR)["distance"] > 1.0


def test_mstft_ignores_level(ping):
    """Loudness is matched first, so a quieter copy is still the same timbre."""
    assert analysis.mstft_distance(ping, ping * 0.25, SR)["distance"] < 1e-6


def test_wav_roundtrip(tmp_path):
    x = np.sin(np.linspace(0, 80, 4800)).astype(np.float32)
    p = capture.save_wav(x, SR, tmp_path / "t.wav")
    back, sr = capture.load_wav(p)
    assert sr == SR
    assert np.allclose(back, x, atol=1e-3)


def test_display_scaling_round_trips_the_documented_range():
    tune = SECTIONS["fm_drum"]["tune"]           # displays -60 to +60
    assert section_tool.to_midi_value(tune, 0)[0] == 64
    assert section_tool.to_midi_value(tune, -60)[0] == 0
    assert section_tool.to_midi_value(tune, 60)[0] == 127
    assert section_tool.to_midi_value(tune, 99)[0] is None


def test_display_scaling_handles_a_small_enum():
    algo = SECTIONS["fm_drum"]["algo"]           # displays 1 to 7
    assert section_tool.to_midi_value(algo, 1)[0] == 0
    assert section_tool.to_midi_value(algo, 7)[0] == 6


def test_named_options_resolve_and_reject():
    dest = SECTIONS["lfo1"]["dest"]
    value, error = section_tool.to_midi_value(dest, "filter_freq")
    assert error is None and value == 67
    assert section_tool.to_midi_value(dest, "nope")[0] is None


def test_apply_sends_cc_and_records_state():
    midi = FakeMidi()
    store.TRACK_STATE.clear()
    out = section_tool._apply(midi, "fm_drum", 3, {"gran": 78, "nlev": 110})
    assert out["sent"] == {"gran": 78, "nlev": 110}
    assert midi.ccs == [(3, 76, 78), (3, 77, 110)]
    assert store.TRACK_STATE.get(3)["fm_drum"] == {"gran": 78, "nlev": 110}


def test_apply_clamps_out_of_range_midi_values():
    midi = FakeMidi()
    section_tool._apply(midi, "fm_drum", 1, {"gran": 999, "nlev": -5})
    assert sorted(v for _, _, v in midi.ccs) == [0, 127]


def test_nrpn_path_is_used_when_asked():
    midi = FakeMidi()
    section_tool._apply(midi, "fm_drum", 1, {"gran": 64}, use_nrpn=True)
    assert midi.nrpns and midi.nrpns[0][0] == 1
    assert midi.ccs == []


def test_nrpn_falls_back_to_cc_when_it_fails():
    """Not every parameter answers to NRPN; a refusal must not lose the value."""
    midi = FakeMidi(nrpn_ok=False)
    out = section_tool._apply(midi, "fm_drum", 1, {"gran": 64}, use_nrpn=True)
    assert out["sent"] == {"gran": 64}
    assert midi.ccs == [(1, 76, 64)]


def test_apply_rejects_bad_track_and_units():
    midi = FakeMidi()
    assert "error" in section_tool._apply(midi, "fm_drum", 0, {"gran": 1})
    assert "error" in section_tool._apply(
        midi, "fm_drum", 1, {"gran": 1}, units="bogus"
    )


def test_apply_sections_reports_unknown_names():
    midi = FakeMidi()
    out = section_tool.apply_sections(
        midi, 2, {"fm_drum": {"gran": 10, "nope": 5}, "not_a_section": {}}
    )
    assert out["sections"]["fm_drum"]["sent"] == {"gran": 10}
    assert out["unknown"]["fm_drum"] == ["nope"]
    assert "not_a_section" in out["unknown"]


def test_patch_save_load_list_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PATCH_DIR", tmp_path)
    store.save("bells", {"fm_drum": {"gran": 78}}, 1, "test")
    assert [p["name"] for p in store.names()] == ["bells"]
    assert store.load("bells")["sections"]["fm_drum"]["gran"] == 78
    assert store.delete("bells") is True
    assert store.names() == []


def test_patch_name_must_be_usable(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PATCH_DIR", tmp_path)
    with pytest.raises(ValueError):
        store.save("///", {}, 1)


def test_morph_endpoints_and_midpoint():
    a = {"s": {"x": 0}}
    b = {"s": {"x": 100}}
    assert store.morph(a, b, 0.0)["s"]["x"] == 0
    assert store.morph(a, b, 1.0)["s"]["x"] == 100
    assert store.morph(a, b, 0.5)["s"]["x"] == 50


def test_mutate_respects_only_and_bounds():
    import random

    base = {"s": {"keep": 64, "move": 64}}
    out = store.mutate(base, 1.0, only=["move"], rng=random.Random(2))
    assert out["s"]["keep"] == 64
    assert 0 <= out["s"]["move"] <= 127


def test_learn_summarises_cc_and_maps_it_back():
    events = [
        (0.0, mido.Message("control_change", channel=0, control=76, value=10)),
        (0.1, mido.Message("control_change", channel=0, control=76, value=90)),
    ]
    out = _summarise(events)
    entry = out["control_changes"]["ch1_cc76"]
    assert (entry["min"], entry["max"], entry["count"]) == (10, 90, 2)
    assert "fm_drum.gran" in entry["maps_to"]


def test_learn_reassembles_nrpn_sequences():
    events = [
        (0.0, mido.Message("control_change", channel=0, control=99, value=1)),
        (0.0, mido.Message("control_change", channel=0, control=98, value=79)),
        (0.0, mido.Message("control_change", channel=0, control=6, value=64)),
    ]
    out = _summarise(events)
    assert out["nrpn"] == [{"channel": 1, "msb": 1, "lsb": 79, "data_msb": 64}]


def test_learn_explains_an_empty_capture():
    assert "Send CC/NRPN" in _summarise([])["note"]


def test_new_tools_are_registered():
    from elektron_mcp.mcp_server.server import mcp

    names = {t.name for t in asyncio.run(mcp.list_tools())}
    for name in (
        "audition", "audition_sequence", "capture_and_analyze",
        "analyze_wav_file", "score_against_reference", "list_audio_inputs",
        "snapshot_patch", "recall_patch", "list_patches", "delete_patch",
        "diff_patches", "morph_patches", "mutate_patch", "get_track_state",
        "clear_track_state", "start_midi_capture", "get_captured_midi",
        "stop_midi_capture", "listen_for_midi", "identify_cc",
        "set_enum_parameter",
    ):
        assert name in names, f"{name} not registered"


def test_section_tools_expose_units_and_nrpn():
    from elektron_mcp.mcp_server.server import mcp

    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    for section in SECTIONS:
        props = tools[f"set_{section}"].inputSchema["properties"]
        assert "units" in props and "use_nrpn" in props


def test_onset_count_ignores_tremolo_in_a_sustained_tone():
    """Regression: a fixed fraction-of-peak threshold counted a 6 Hz tremolo
    as dozens of attacks, which made a sustained patch look like a shaker."""
    t = np.arange(SR // 2) / SR
    trem = (
        np.sin(2 * np.pi * 440 * t)
        * (1 + 0.3 * np.sin(2 * np.pi * 6 * t))
        * np.exp(-t * 1.5)
    )
    assert analysis.onset_count(trem, SR) <= 2


def test_apply_scales_display_units_end_to_end():
    midi = FakeMidi()
    out = section_tool._apply(
        midi, "fm_drum", 1, {"tune": 24, "algo": 7}, units="display"
    )
    assert out["sent"] == {"tune": 89, "algo": 6}
    assert (1, 40, 89) in midi.ccs


def test_apply_reports_display_values_out_of_range():
    midi = FakeMidi()
    out = section_tool._apply(midi, "fm_drum", 1, {"tune": 500}, units="display")
    assert "tune" in out["out_of_range"]
    assert out["sent"] == {}


class FakeNoteMidi:
    """Records notes without touching hardware."""

    def __init__(self):
        self.notes = []

    def send_note_on(self, track, note, velocity):
        self.notes.append(("on", track, note, velocity))
        return True

    def send_note_off(self, track, note):
        self.notes.append(("off", track, note))
        return True


def test_trigger_falls_back_to_a_child_process(monkeypatch):
    """A long-lived server can lose the ability to reopen the audio device.

    The note must still be played, and the capture must still be returned,
    via the subprocess path.
    """
    from elektron_mcp.tools import audition_tool

    class BrokenRecorder:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            raise capture.CaptureError("simulated paInternalError -9986")

        def __exit__(self, *exc):
            return False

    seen = {}

    class FakeSubprocessRecorder:
        def __init__(self, seconds, device=None, **k):
            seen["seconds"] = seconds

        def start(self):
            seen["started"] = True
            return self

        def finish(self):
            return np.zeros((480, 2), dtype=np.float32), 48000

    monkeypatch.setattr(capture, "Recorder", BrokenRecorder)
    monkeypatch.setattr(capture, "SubprocessRecorder", FakeSubprocessRecorder)

    midi = FakeNoteMidi()
    audio, sr = audition_tool._trigger_and_capture(
        midi, 3, 84, 100, 20, 20, "device"
    )

    assert seen.get("started") is True
    assert sr == 48000 and len(audio) == 480
    # The window has to cover settle + note + tail, not just the note.
    assert seen["seconds"] > 0.04
    assert ("on", 3, 84, 100) in midi.notes and ("off", 3, 84) in midi.notes


def test_subprocess_recorder_reports_a_bad_device():
    with pytest.raises(capture.CaptureError):
        capture.SubprocessRecorder(0.1, device="No Such Device 99999").start()


def test_subprocess_recorder_errors_if_never_started():
    with pytest.raises(capture.CaptureError):
        capture.SubprocessRecorder(0.1).finish()
