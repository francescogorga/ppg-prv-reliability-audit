"""Tests for the Python port (app_pipeline.py).

1. Equivalence with the ORIGINAL Dart code, run by dart_ref/ref.dart on seeded
   synthetic signals (regenerate with dart_ref/gen_reference.py).
2. Independent checks on synthetic signals with known ground truth.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import signal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app_pipeline as ap  # noqa: E402
from synthetic import make_cases  # noqa: E402

OUT = ROOT / "dart_ref" / "out"
CASES = make_cases()


def _load_dart(name, gate):
    prefix = OUT / f"{name}_gate{gate}"
    s = np.genfromtxt(f"{prefix}_samples.csv", delimiter=",", names=True)
    t = np.genfromtxt(f"{prefix}_ticks.csv", delimiter=",", names=True, missing_values="", filling_values=np.nan)
    iv_txt = Path(f"{prefix}_intervals.csv").read_text().split()
    iv = np.array([float(v) for v in iv_txt]) if iv_txt else np.array([])
    return s, t, iv


@pytest.mark.parametrize("name", sorted(CASES))
@pytest.mark.parametrize("gate", ["0.4", "none"])
def test_matches_dart(name, gate):
    fs, raw, _bt, _rr = CASES[name]
    # Dart parsed the same repr() strings, so both sides start from identical doubles
    res = ap.run_session([float(v) for v in raw], fs=fs, gate=None if gate == "none" else float(gate))
    s, t, iv = _load_dart(name, gate)
    assert len(res.filtered) == len(s)
    np.testing.assert_allclose(res.filtered, s["filtered"], rtol=0, atol=1e-9)
    assert np.array_equal(np.array(res.peak, dtype=int), s["peak"].astype(int))
    np.testing.assert_allclose(res.sqi_after, s["sqi_after"], rtol=0, atol=1e-12)
    # 1 Hz ticks: RMSSD and number of stored intervals
    py_rmssd = np.array([k["rmssd"] for k in res.ticks])
    py_n = np.array([k["n_intervals"] for k in res.ticks])
    np.testing.assert_allclose(py_rmssd, t["rmssd"], rtol=0, atol=1e-9)
    assert np.array_equal(py_n, t["n_intervals"].astype(int))
    # final interval buffer (last <=60 accepted RR)
    np.testing.assert_allclose(res.accepted_intervals_ms[-60:], iv, rtol=0, atol=1e-9)


@pytest.mark.parametrize("fs,fc", [(100.0, 0.5), (64.0, 0.5), (125.0, 0.5), (500.0, 0.5)])
def test_highpass_equals_scipy_butterworth(fs, fc):
    bq = ap.make_highpass(fs, fc)
    b, a = signal.butter(2, fc, btype="high", fs=fs)
    np.testing.assert_allclose([bq.b0, bq.b1, bq.b2], b, rtol=1e-12)
    np.testing.assert_allclose([1.0, bq.a1, bq.a2], a, rtol=1e-12)


@pytest.mark.parametrize("fs,fc", [(100.0, 3.5), (64.0, 3.5), (125.0, 3.5), (500.0, 3.5)])
def test_lowpass_equals_scipy_butterworth(fs, fc):
    bq = ap.make_lowpass(fs, fc)
    b, a = signal.butter(2, fc, btype="low", fs=fs)
    np.testing.assert_allclose([bq.b0, bq.b1, bq.b2], b, rtol=1e-12)
    np.testing.assert_allclose([1.0, bq.a1, bq.a2], a, rtol=1e-12)


def test_bandpass_minus3db_at_cutoffs():
    fs = 100.0
    hp, lp = ap.make_highpass(fs, 0.5), ap.make_lowpass(fs, 3.5)
    for bq, fc in [(hp, 0.5), (lp, 3.5)]:
        _, h = signal.freqz([bq.b0, bq.b1, bq.b2], [1, bq.a1, bq.a2], worN=[fc], fs=fs)
        assert abs(20 * np.log10(abs(h[0])) + 3.0103) < 0.01


def test_rmssd_known_values():
    assert ap.compute_rmssd([800, 810, 790, 800]) == pytest.approx(math.sqrt((100 + 400 + 100) / 3))
    assert ap.compute_rmssd([800]) == 0.0


def test_dart_round_half_away_from_zero():
    assert ap.dart_round(2.5) == 3 and ap.dart_round(0.5) == 1 and ap.dart_round(-2.5) == -3


@pytest.mark.parametrize("name", ["clean_nose_100hz", "clean_nose_64hz", "clean_finger_125hz"])
def test_clean_signal_recovers_hr_and_rmssd(name):
    fs, raw, _bt, rr = CASES[name]
    # Flip to blood-volume polarity so the detector's maxima are the systolic peaks.
    # On raw (light) polarity the maxima fall on the pulse foot, which in this
    # Gaussian synthetic model is ill-defined (see test_raw_polarity_* below).
    vol = 2 * np.median(raw) - raw
    res = ap.run_session(list(vol), fs=fs, gate=None)
    iv = np.array(res.accepted_intervals_ms)
    assert len(iv) > 0.8 * len(rr)  # most beats recovered
    true_hr = 60000 / np.median(rr)
    assert abs(60000 / np.median(iv) - true_hr) < 2.0
    true_rmssd = ap.compute_rmssd(list(rr))
    assert abs(ap.compute_rmssd(list(iv)) - true_rmssd) < 0.10 * true_rmssd


def test_raw_polarity_on_synthetic_overestimates_rmssd():
    """Documents a property of the synthetic model, not of real data: on raw light
    polarity the app's maxima land on the foot and RMSSD is inflated."""
    fs, raw, _bt, rr = CASES["clean_nose_100hz"]
    res = ap.run_session(list(raw), fs=fs, gate=None)
    assert ap.compute_rmssd(res.accepted_intervals_ms) > 1.2 * ap.compute_rmssd(list(rr))


def test_sqi_zero_when_sensor_off():
    fs, raw, _bt, _rr = CASES["sensor_off_100hz"]
    res = ap.run_session(list(raw), fs=fs, gate=0.4)
    sqi = np.array(res.sqi_after)
    # window fully inside the 'off' segment (60-80 s) -> presence check (DC < 10)
    assert np.all(sqi[int(70 * fs): int(80 * fs)] == 0.0)


def test_gate_above_04_can_never_bootstrap():
    """With no intervals yet, periodicity=0 so SQI <= 0.40: a gate > 0.4 accepts nothing."""
    fs, raw, _bt, _rr = CASES["clean_nose_100hz"]
    res = ap.run_session(list(raw), fs=fs, gate=0.41)
    assert len(res.accepted_intervals_ms) == 0
