import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app_pipeline as ap  # noqa: E402
from ecg_rpeaks import detect_r_peaks, match, rmssd_clean  # noqa: E402
from synthetic import make_cases  # noqa: E402


def _synthetic_ecg(fs=128.0, seed=7):
    rng = np.random.default_rng(seed)
    rr = 0.8 + 0.04 * rng.standard_normal(200)
    r = np.cumsum(rr) + 1.0
    t = np.arange(int((r[-1] + 1) * fs)) / fs
    x = np.zeros_like(t)
    for tr in r:  # narrow R wave + small T wave
        x += np.exp(-0.5 * ((t - tr) / 0.012) ** 2) + 0.25 * np.exp(-0.5 * ((t - tr - 0.25) / 0.05) ** 2)
    x += 0.03 * rng.standard_normal(len(t)) + 0.2 * np.sin(2 * np.pi * 0.3 * t)
    return x, r, fs


def test_rpeaks_on_synthetic_ecg():
    x, r, fs = _synthetic_ecg()
    det = detect_r_peaks(x * 1000, fs)
    se, ppv, err = match(det, r, tol=0.05)
    assert se > 0.99 and ppv > 0.99
    assert np.median(np.abs(err)) < 0.004  # sub-sample refinement at 128 Hz (7.8 ms grid)


def test_rmssd_clean_ignores_a_missed_beat():
    r = np.cumsum(np.full(80, 0.8)) + np.r_[0, np.tile([0.01, -0.01], 40)[:79]]
    full = rmssd_clean(r, 0, 100)[0]
    missed = rmssd_clean(np.delete(r, 40), 0, 100)[0]
    assert abs(full - missed) < 1.0


def test_record_sqi_flag_does_not_change_peaks():
    fs, raw, _bt, _rr = make_cases()["motion_nose_100hz"]
    a = ap.run_session(list(raw), fs=fs, gate=0.4)
    b = ap.run_session(list(raw), fs=fs, gate=0.4, record_sqi=False)
    assert a.peak == b.peak and a.accepted_intervals_ms == b.accepted_intervals_ms
    assert b.sqi_after == []
