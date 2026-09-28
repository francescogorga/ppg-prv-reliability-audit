"""v2 (systolic-peak timing): only the detector input changes."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app_pipeline as ap  # noqa: E402
from synthetic import make_cases  # noqa: E402

CASES = make_cases()


def test_v1_default_unchanged():
    fs, raw, _bt, _rr = CASES["motion_nose_100hz"]
    a = ap.run_session(list(raw), fs=fs, gate=0.4)
    b = ap.run_session(list(raw), fs=fs, gate=0.4, systolic=False)
    assert a.peak == b.peak and a.sqi_after == b.sqi_after


def test_v2_detects_on_negated_filtered_signal():
    fs, raw, _bt, _rr = CASES["clean_nose_100hz"]
    v1 = ap.run_session(list(raw), fs=fs, gate=None)
    v2 = ap.run_session(list(raw), fs=fs, gate=None, systolic=True)
    assert v1.filtered == v2.filtered              # same filter output
    det = ap.PeakDetector(fs=fs, threshold_sigma=0.8, window_ms=4000, refractory_ms=400)
    ref = [False] + [det.process(-f) for f in v1.filtered[1:]]  # first packet is not filtered
    assert v2.peak == ref


def test_v2_recovers_rmssd_on_raw_light_polarity():
    # the case where v1 inflates RMSSD (tests/test_port.py::test_raw_polarity_...)
    for name in ("clean_nose_100hz", "clean_nose_64hz", "clean_finger_125hz"):
        fs, raw, _bt, rr = CASES[name]
        v2 = ap.run_session(list(raw), fs=fs, gate=None, systolic=True)
        true = ap.compute_rmssd(list(rr))
        assert abs(ap.compute_rmssd(v2.accepted_intervals_ms) - true) < 0.10 * true
        assert len(v2.accepted_intervals_ms) > 0.8 * len(rr)
