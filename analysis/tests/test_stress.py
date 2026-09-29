"""The Python stress index must reproduce the app's Dart StressDetector exactly.

Seeded synthetic 1 Hz sequences (baseline, rest, rising HR / falling HRV, recovery,
missing HR, HRV = 0 when too few intervals, gated seconds). The Dart outputs are
stored in dart_ref/out/stress_*.csv (regenerate with dart_ref/gen_stress_reference.py).
"""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stress import TickSeries, simulate  # noqa: E402

OUT = ROOT / "dart_ref" / "out"


def cases(seed=20260928):
    rng = np.random.default_rng(seed)
    res = {}
    n = 600
    t = np.arange(n)
    hr = 70 + 2 * rng.standard_normal(n) + np.where((t > 200) & (t < 400), 25 * np.minimum((t - 200) / 60, 1), 0)
    hrv = 45 + 4 * rng.standard_normal(n) - np.where((t > 200) & (t < 400), 25 * np.minimum((t - 200) / 60, 1), 0)
    res["ramp"] = (hr, hrv, np.ones(n, bool))
    hr2 = hr.copy()
    hr2[:5] = np.nan
    hr2[300:320] = np.nan
    hrv2 = hrv.copy()
    hrv2[:3] = 0.0
    gate = rng.random(n) > 0.2
    res["missing_and_gated"] = (hr2, hrv2, gate)
    flat = np.full(n, 70.0)
    res["flat_baseline"] = (flat + np.where(t > 100, 3.0, 0.0), np.full(n, 40.0) - np.where(t > 100, 2.0, 0.0), np.ones(n, bool))
    return res


def to_series(hr, hrv, gate):
    return TickSeries(hr=[None if np.isnan(x) else float(x) for x in hr], hrv=[float(x) for x in hrv], gate=list(map(bool, gate)))


@pytest.mark.parametrize("name", ["ramp", "missing_and_gated", "flat_baseline"])
def test_stress_matches_dart(name):
    hr, hrv, gate = cases()[name]
    py = simulate(to_series(hr, hrv, gate), 0, len(hr))
    dart = np.genfromtxt(OUT / f"stress_{name}_out.csv", delimiter=",", names=True)
    assert len(py) == len(dart)
    assert [s for s, _ in py] == dart["score"].astype(int).tolist()
    assert [lv for _, lv in py] == dart["level"].astype(int).tolist()


def test_stress_rises_with_hr_and_falls_back():
    hr, hrv, gate = cases()["ramp"]
    py = simulate(to_series(hr, hrv, gate), 0, len(hr))
    scores = np.array([s for s, _ in py])
    assert scores[300:400].mean() > 60 and scores[500:].mean() < 30
