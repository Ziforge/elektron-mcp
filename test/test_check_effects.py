"""The effect measurements, checked against signals whose truth is known.

A hardware verdict is only worth as much as the measurement behind it, and
the sweep's generic "the sound changed" has already been wrong in both
directions. So these build delays and decays by hand, where the right
answer is known exactly, and require the measurements to recover it.
"""

import importlib.util
import os

import numpy as np
import pytest

_PATH = os.path.join(os.path.dirname(__file__), "..", "tools",
                     "check_effects.py")
_spec = importlib.util.spec_from_file_location("check_effects", _PATH)
fx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fx)

SR = 48000


def _burst(length_ms=12, level=1.0):
    n = int(length_ms / 1000 * SR)
    rng = np.random.default_rng(1)
    return rng.standard_normal(n) * level


def _echoes(spacing_ms, count=5, decay=0.65, total_ms=2000):
    """A hit repeated at a fixed spacing -- a delay, built by hand."""
    out = np.zeros(int(total_ms / 1000 * SR))
    for i in range(count):
        start = int(i * spacing_ms / 1000 * SR)
        hit = _burst(level=decay ** i)
        end = min(len(out), start + len(hit))
        if end > start:
            out[start:end] += hit[: end - start]
    return np.stack([out, out], axis=1)


@pytest.mark.parametrize("spacing", [60, 125, 250, 400])
def test_echo_spacing_is_recovered(spacing):
    """Within 10%, which is far tighter than the ranking test needs."""
    measured = fx.echo_lag_ms(_echoes(spacing), SR)
    assert measured is not None
    assert abs(measured - spacing) / spacing < 0.1, (measured, spacing)


def test_a_single_hit_has_no_echo_to_find():
    """So a delay that is not working cannot read as one that is."""
    lone = np.stack([np.concatenate([_burst(), np.zeros(SR)])] * 2, axis=1)
    measured = fx.echo_lag_ms(lone, SR)
    # Either nothing, or nothing resembling a real repeat.
    assert measured is None or measured > 500


def test_silence_measures_nothing_rather_than_something():
    assert fx.echo_lag_ms(np.zeros((SR, 2)), SR) is None
    assert fx.repeat_count(np.zeros((SR, 2)), SR) == 0


@pytest.mark.parametrize("count", [1, 3, 6])
def test_repeats_are_counted(count):
    audio = _echoes(200, count=count, decay=0.95, total_ms=2000)
    assert fx.repeat_count(audio, SR) == count


def test_more_feedback_reads_as_more_repeats():
    """The shape the feedback check relies on."""
    few = fx.repeat_count(_echoes(200, count=2, decay=0.3), SR)
    many = fx.repeat_count(_echoes(200, count=6, decay=0.95), SR)
    assert many > few


def test_decay_measurement_tracks_a_longer_tail():
    """What the reverb check rests on: a longer tail must measure longer."""
    from rig_audio.analysis import decay_time_ms

    times = []
    for tau_ms in (80, 300, 900):
        t = np.arange(int(1.8 * SR)) / SR
        env = np.exp(-t / (tau_ms / 1000))
        rng = np.random.default_rng(2)
        times.append(decay_time_ms(rng.standard_normal(len(t)) * env, SR))
    assert all(t is not None for t in times)
    assert times[0] < times[1] < times[2], times


def test_rank_correlation_behaves():
    assert fx.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert fx.spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
    # Proportional-but-not-linear still ranks perfectly, which is why rank
    # correlation is the test and not a straight-line fit.
    assert fx.spearman([1, 2, 3, 4], [1, 4, 9, 16]) == pytest.approx(1.0)
    assert fx.spearman([1, 2], [2, 1]) == 0.0


def test_a_flat_response_fails_the_correlation():
    """A parameter that changes nothing must not pass as working."""
    assert fx.spearman([1, 2, 3, 4], [5, 5, 5, 5]) == 0.0


def test_spread_measures_how_far_a_reading_moved():
    assert fx.spread([55.0, 55.1, 55.0, 55.2]) < 0.01
    assert fx.spread([60.0, 500.0]) > 0.8
    assert fx.spread([]) == 0.0


def test_a_near_flat_response_must_not_pass_on_ranking_alone():
    """Four reverb tails measuring 55 ms, differing only by noise in the
    decimals, ranked at rho +0.949 and passed. Ranking says the response
    is ordered, not that there is one."""
    tails = [55.02, 55.07, 55.11, 55.19]
    assert fx.spearman([10, 45, 80, 120], tails) > 0.9
    assert fx.spread(tails) < 0.25


def test_late_energy_rises_with_a_longer_tail():
    """What the reverb check rests on. T20 could not see this: the dry hit
    falls 20 dB long before any tail matters, so T20 read the same 55 ms at
    every decay setting."""
    readings = []
    for tau_ms in (40, 400, 1500):
        t = np.arange(int(2.4 * SR)) / SR
        rng = np.random.default_rng(3)
        hit = rng.standard_normal(len(t)) * np.exp(-t / 0.03)
        tail = rng.standard_normal(len(t)) * np.exp(-t / (tau_ms / 1000))
        audio = np.stack([hit + tail * 0.3] * 2, axis=1)
        readings.append(fx.late_energy(audio, SR))
    assert readings[0] < readings[1] < readings[2], readings
    assert fx.spread(readings) > 0.25


def test_late_energy_is_zero_for_silence_and_for_a_bare_hit():
    assert fx.late_energy(np.zeros((SR, 2)), SR) == 0.0
    t = np.arange(int(2.4 * SR)) / SR
    bare = np.exp(-t / 0.02) * np.random.default_rng(4).standard_normal(len(t))
    assert fx.late_energy(np.stack([bare] * 2, axis=1), SR) < 0.05


def test_the_echo_search_reaches_past_a_second():
    """A fixed 900 ms ceiling made the two longest delay settings read as
    no echo at all, when the device was tracking at about 11 ms per unit."""
    measured = fx.echo_lag_ms(_echoes(1100, count=3, total_ms=4000), SR)
    assert measured is not None
    assert abs(measured - 1100) / 1100 < 0.1, measured
