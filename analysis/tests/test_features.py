"""Sanity checks for features.py on seeded synthetic signals (not real data)."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app_pipeline as ap  # noqa: E402
from features import FEATURES, window_features  # noqa: E402
from run_analysis import tick_frame  # noqa: E402
from synthetic import make_cases  # noqa: E402


def _feats(raw, fs, t0, t1):
    s = ap.run_session(list(raw), fs, gate=None, record_per_sample=True, record_sqi=False, tick_parts=True, systolic=True)
    peaks = np.flatnonzero(np.asarray(s.peak)) - 1
    acc = np.zeros(int(len(raw) / fs * 100))
    return window_features(s, fs, np.asarray(s.filtered), peaks, tick_frame(s, fs), acc, 100.0, t0, t1)


def test_all_features_present():
    fs, raw, _bt, _rr = make_cases()["clean_nose_100hz"]
    f = _feats(raw, fs, 20, 80)
    assert set(f) == set(FEATURES)


def test_template_correlation_drops_with_motion():
    c = make_cases()
    fs, clean, _, _ = c["clean_nose_100hz"]
    _, motion, _, _ = c["motion_nose_100hz"]          # motion bursts at 40-55 s and 80-90 s
    fc, fm = _feats(clean, fs, 35, 95), _feats(motion, fs, 35, 95)
    assert fc["tmpl_corr_mean"] > 0.95
    assert fm["tmpl_corr_mean"] < fc["tmpl_corr_mean"] - 0.05
    assert fm["reject_frac"] >= fc["reject_frac"]
