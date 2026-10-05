"""The measurement logic behind the hardware sweep, without hardware.

These cover the parts that produced wrong answers when they were wrong:
the section scoping, the onset window, and how a verdict is reached.
"""

import importlib.util
import os

import numpy as np
import pytest

_PATH = os.path.join(os.path.dirname(__file__), "..", "tools",
                     "sweep_device.py")
_spec = importlib.util.spec_from_file_location("sweep_device", _PATH)
sweep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sweep)


def _note(samplerate=48000, lead_ms=50, length_ms=400, level=0.5):
    """Silence, then a burst -- a crude stand-in for a struck note."""
    lead = np.zeros((int(lead_ms / 1000 * samplerate), 2))
    body = np.full((int(length_ms / 1000 * samplerate), 2), level)
    tail = np.zeros((int(0.2 * samplerate), 2))
    return np.concatenate([lead, body, tail])


def test_two_machines_in_one_patch_is_detected_as_a_collision():
    """The machines share CC 40 to 47 by design, so a patch holding two of
    them leaves only the last one written standing. A sweep that did this
    had 29 of 30 FM DRUM parameters overwritten before the note sounded."""
    from elektron_mcp.digitone.data.sections import SECTIONS

    both = {"fm_drum": SECTIONS["fm_drum"], "fm_tone": SECTIONS["fm_tone"]}
    clashes = sweep.collisions_in(both)
    assert len(clashes) >= 8
    assert any("CC 40" in c for c in clashes)

    # And the set the sweep actually uses is clean.
    assert sweep.collisions_in(
        sweep.sections_for("fm_drum", "filter_multi_mode")) == []


def test_a_compatible_set_has_no_cc_collisions():
    sections = sweep.sections_for("fm_drum", "filter_multi_mode")
    claims = {}
    for name, params in sections.items():
        for ident, spec in params.items():
            cc = sweep.cc_of(spec)
            if cc is None:
                continue
            assert cc not in claims, (cc, claims.get(cc), f"{name}.{ident}")
            claims[cc] = f"{name}.{ident}"
    assert "fm_tone" not in sections and "wavetone" not in sections


def test_align_trims_to_the_onset():
    """Not shift invariant: a note landing later must not read as a
    different sound."""
    sr = 48000
    early = sweep.align(_note(sr, lead_ms=10), sr, keep=0.3)
    late = sweep.align(_note(sr, lead_ms=120), sr, keep=0.3)
    assert early.shape == late.shape
    assert np.allclose(early, late)


def test_align_window_selects_a_slice_measured_from_the_onset():
    sr = 48000
    audio = _note(sr, lead_ms=50, length_ms=400, level=0.5)
    # 0-100 ms after the onset is inside the burst.
    inside = sweep.align(audio, sr, window=(0, 100))
    assert abs(float(inside.mean()) - 0.5) < 1e-6
    # 500-600 ms after the onset is past its end, so silence.
    beyond = sweep.align(audio, sr, window=(500, 600))
    assert float(np.abs(beyond).max()) == 0.0
    assert len(beyond) == int(0.1 * sr)


def test_align_pads_a_window_past_the_recording():
    sr = 48000
    audio = _note(sr, length_ms=100)
    out = sweep.align(audio, sr, window=(0, 2000))
    assert len(out) == int(2.0 * sr)


def test_balance_reads_the_stereo_position():
    """A mono-summed distance cannot see panning at all, so pan verifies
    only through this."""
    centred = np.ones((100, 2))
    assert sweep.balance(centred) == pytest.approx(0.5)
    hard_left = np.zeros((100, 2))
    hard_left[:, 0] = 1.0
    assert sweep.balance(hard_left) == pytest.approx(1.0)
    assert sweep.balance(np.zeros((100, 2))) == pytest.approx(0.5)


def test_descriptor_deltas_are_fractions_of_the_larger_value():
    deltas = sweep.descriptor_deltas(
        {"rms": 0.02, "spectral_centroid_hz": 1000.0},
        {"rms": 0.04, "spectral_centroid_hz": 1000.0},
    )
    assert deltas["level"] == pytest.approx(0.5)
    assert deltas["brightness"] == pytest.approx(0.0)


def test_changed_descriptors_respects_a_measured_floor():
    """The floor is measured per run because how much a descriptor wanders
    depends on the material: a quiet decaying tail wanders far more than a
    struck note."""
    ref = {"spectral_centroid_hz": 1000.0}
    probe = {"spectral_centroid_hz": 1200.0}
    assert "brightness" in sweep.changed_descriptors(
        ref, probe, {"brightness": 0.05})
    assert sweep.changed_descriptors(ref, probe, {"brightness": 0.9}) == {}
    # A descriptor with no measured floor is not guessed at.
    assert sweep.changed_descriptors(ref, probe, {}) == {}


def test_missing_descriptors_are_skipped_not_guessed():
    deltas = sweep.descriptor_deltas({"rms": None}, {"rms": 0.5})
    assert "level" not in deltas


def test_probe_values_try_both_ends():
    """A parameter can be inert at one end and alive at the other."""
    assert sweep.probe_values({"cc_msb": 1}) == [127, 0]
    assert sweep.probe_values({"cc_msb": 1, "max_midi": 6}) == [6, 0]


def test_amp_profiles_differ_in_sustain():
    """The percussive note keeps probes quick but ends before a later
    envelope stage or an LFO cycle can be heard."""
    assert sweep.AMP_PROFILES["percussive"]["sus"] == 0
    assert sweep.AMP_PROFILES["sustained"]["sus"] > 100


def test_unusable_floor_constant_is_set_from_what_was_observed():
    """One configuration measured 2.31 against itself; anything that far
    from zero makes every verdict taken against it noise."""
    assert 0 < sweep.FLOOR_UNUSABLE < 2.31


def test_a_cc_only_collides_within_one_channel():
    """The send effects answer on the FX control channel, so their CC
    numbers are free to repeat the track's -- and do. Treating those as
    clashes kept 43 parameters out of the sweep for no reason."""
    track_only = sweep.sections_for("fm_drum", "filter_multi_mode")
    with_fx = sweep.sections_for("fm_drum", "filter_multi_mode",
                                 fx_channel=9)
    assert sweep.collisions_in(track_only) == []
    assert sweep.collisions_in(with_fx) == []
    assert len(with_fx) > len(track_only)

    # The overlap is real, which is why it has to be the channel that
    # separates them and not luck.
    from elektron_mcp.digitone.data.sections import SECTIONS
    chorus = {int(s["cc_msb"]) for s in SECTIONS["send_chorus"].values()}
    source = {int(s["cc_msb"]) for s in SECTIONS["fm_drum"].values()}
    assert chorus & source


def test_sections_route_to_their_own_channel():
    device = sweep.Device.__new__(sweep.Device)
    device.channel = 13          # track 14, zero-based
    device.fx_channel = 8        # FX control channel 9, zero-based
    assert device.channel_for("fm_drum") == 13
    assert device.channel_for("amp") == 13
    assert device.channel_for("send_reverb") == 8
    assert device.channel_for("compressor") == 8


def test_an_fx_section_without_its_channel_is_refused():
    """Silently sending it to the track's channel would set whatever the
    track happens to have on that CC instead."""
    device = sweep.Device.__new__(sweep.Device)
    device.channel = 13
    device.fx_channel = None
    assert device.channel_for("amp") == 13
    with pytest.raises(ValueError, match="FX control channel"):
        device.channel_for("send_reverb")


def test_the_spectral_distance_is_level_invariant():
    """Worth pinning, because it is the reason the harness needs the
    descriptors at all. mstft_distance RMS-normalises both signals before
    comparing, so a parameter that only changes loudness -- a volume, a
    send, the compressor's dry/wet -- is invisible to it."""
    from rig_audio.analysis import mstft_distance

    sr = 48000
    rng = np.random.default_rng(0)
    quiet = rng.standard_normal((sr, 2)) * 0.05
    loud = quiet * 4.0
    assert mstft_distance(quiet, loud, sr)["distance"] < 0.01

    # The level descriptor is what notices it.
    deltas = sweep.descriptor_deltas({"rms": 0.05}, {"rms": 0.20})
    assert deltas["level"] > 0.5


def test_the_lock_names_a_live_owner_and_ignores_a_stale_one(tmp_path,
                                                             monkeypatch):
    """Two sweeps at once interleave their patch writes to one instrument,
    and every reading becomes noise -- a parameter proven to silence the
    device read as no change at all under that. A stale lock from a killed
    run must not block the next one either."""
    lock = tmp_path / "sweep.lock"
    monkeypatch.setattr(sweep, "LOCK_PATH", str(lock))

    assert sweep.acquire_lock() is None
    assert lock.read_text().strip() == str(os.getpid())

    # A second attempt from this same process sees a live owner.
    assert sweep.acquire_lock() == os.getpid()

    # A lock naming a process that no longer exists is taken over.
    lock.write_text("999999")
    assert sweep.acquire_lock() is None

    # Garbage is treated as stale rather than crashing.
    lock.write_text("not-a-pid")
    assert sweep.acquire_lock() is None

    sweep.release_lock()
    assert not lock.exists()


def test_set_in_resolves_the_channel_from_the_section():
    """The probe path once called send_param without a channel, so every
    FX parameter was sent to the track's channel, where its CC number
    means something else. That inverted two verdicts: the pattern volume
    read as doing nothing, and an external input with nothing plugged into
    it read as responding. set_in works the channel out itself so a caller
    cannot leave it off."""
    sent = []

    class FakePort:
        def send(self, message):
            sent.append((message.channel, message.control, message.value))

    device = sweep.Device.__new__(sweep.Device)
    device.channel = 13
    device.fx_channel = 8
    device.port = FakePort()

    device.set_in("amp", {"cc_msb": 90}, 100)
    device.set_in("compressor", {"cc_msb": 119}, 0)

    assert sent == [(13, 90, 100), (8, 119, 0)]


def test_silence_is_asserted_rather_than_polled_when_possible():
    """Polling reopened the audio device up to fourteen times per capture,
    which across one survey is over a thousand opens; CoreAudio stopped
    handing it back and the run died. All Sound Off cuts the note outright,
    so there is nothing to wait for."""
    calls = []

    class FakeDevice:
        def silence(self):
            calls.append("silence")

    def boom(*_args, **_kwargs):
        raise AssertionError("the audio device must not be opened here")

    import rig_audio.capture as cap
    original = cap.record
    sweep.record = boom
    try:
        assert sweep.wait_for_silence("whatever", FakeDevice()) is True
    finally:
        sweep.record = original
    assert calls == ["silence"]
