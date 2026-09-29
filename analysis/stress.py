"""Line-by-line port of the app's stress index (stress_detector.dart), plus the 1 Hz
loop of home_page.dart:212-247. Verified against the original Dart class in
tests/test_stress.py (dart_ref/stress_ref.dart).

Score 0-100 from HR and RMSSD only: z-scores against a 60 s personal baseline,
12 s rolling means, EMA (alpha 0.35), levels with hysteresis (35/25, 65/55).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app_pipeline import dart_round

UNKNOWN, CALM, AROUSED, STRESSED = 0, 1, 2, 3
LEVEL_NAMES = {UNKNOWN: "unknown", CALM: "calm", AROUSED: "aroused", STRESSED: "stressed"}


class _Rolling:
    def __init__(self, capacity):
        self.capacity, self.v = capacity, []

    def add(self, x):
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return
        self.v.append(x)
        if len(self.v) > self.capacity:
            self.v.pop(0)

    @property
    def mean(self):
        if not self.v:
            return None
        s = 0.0
        for x in self.v:
            s += x
        return s / len(self.v)

    def clear(self):
        self.v.clear()


def _std_from(s, sq, n):
    if n < 2:
        return 0.0
    m = s / n
    var = sq / n - m * m
    return math.sqrt(var) if var > 0 else 0.0


def _z01(z):
    if z <= 0:
        return 0.0
    if z >= 2.5:
        return 1.0
    return z / 2.5


class StressDetector:
    def __init__(self, baseline_seconds=60, update_rate_hz=1, slow_window_seconds=12):
        self.baseline_seconds, self.rate = baseline_seconds, update_rate_hz
        cap = slow_window_seconds * update_rate_hz
        self._hr, self._hrv = _Rolling(cap), _Rolling(cap)
        self.base_hr = self.base_hrv = self.sd_hr = self.sd_hrv = None
        self._acq = False
        self._ticks = self._target = 0
        self._level = UNKNOWN
        self._ema = None
        self._reset_sums()

    def _reset_sums(self):
        self._s_hr = self._s_hrv = self._q_hr = self._q_hrv = 0.0
        self._n_hr = self._n_hrv = 0

    @property
    def has_baseline(self):
        return self.base_hr is not None

    def start_baseline(self):
        self.base_hr = self.base_hrv = self.sd_hr = self.sd_hrv = None
        self._reset_sums()
        self._hr.clear()
        self._hrv.clear()
        self._acq = True
        self._ticks = 0
        self._target = self.baseline_seconds * self.rate
        self._level = UNKNOWN
        self._ema = None

    def update(self, hr, hrv):
        self._hr.add(hr)
        self._hrv.add(hrv)
        if not self._acq:
            return
        self._ticks += 1
        if hr is not None and not math.isnan(hr):
            self._s_hr += hr
            self._q_hr += hr * hr
            self._n_hr += 1
        if hrv is not None and not math.isnan(hrv):
            self._s_hrv += hrv
            self._q_hrv += hrv * hrv
            self._n_hrv += 1
        if self._ticks >= self._target:
            if self._n_hr > 0:
                self.base_hr = self._s_hr / self._n_hr
                self.sd_hr = _std_from(self._s_hr, self._q_hr, self._n_hr)
                self.base_hrv = self._s_hrv / self._n_hrv if self._n_hrv > 0 else None
                self.sd_hrv = _std_from(self._s_hrv, self._q_hrv, self._n_hrv) if self._n_hrv > 1 else None
                self._acq = False
            else:
                self._acq = False
                self._ticks = 0

    def compute(self):
        if not self.has_baseline:
            return 0, UNKNOWN
        hr, hrv = self._hr.mean, self._hrv.mean
        arousal = weight = 0.0
        if hr is not None and self.base_hr is not None:
            sd = max(self.sd_hr if self.sd_hr is not None else 2.0, 2.0)
            arousal += 0.5 * _z01((hr - self.base_hr) / sd)
            weight += 0.5
        if hrv is not None and self.base_hrv is not None:
            sd = max(self.sd_hrv if self.sd_hrv is not None else 5.0, 5.0)
            arousal += 0.5 * _z01((self.base_hrv - hrv) / sd)
            weight += 0.5
        if weight < 1e-6:
            return 0, UNKNOWN
        raw = min(max(arousal / weight * 100.0, 0.0), 100.0)
        self._ema = raw if self._ema is None else 0.35 * raw + 0.65 * self._ema
        score = dart_round(self._ema)
        self._level = self._hyst(score)
        return score, self._level

    def _hyst(self, s):
        lv = self._level
        if lv == STRESSED:
            if s < 55:
                lv = AROUSED
        elif lv == AROUSED:
            if s >= 65:
                lv = STRESSED
            elif s < 25:
                lv = CALM
        else:  # calm or unknown
            lv = STRESSED if s >= 65 else AROUSED if s >= 35 else CALM
        self._level = lv
        return lv


@dataclass
class TickSeries:
    hr: list          # per second, None when unavailable (app: heartRateBpm null)
    hrv: list         # per second (app: computeRmssd, 0.0 when < 2 intervals)
    gate: list        # per second, True if the stress detector may update (app: SQI >= 0.4)


def simulate(ts: TickSeries, start: int, n: int):
    """Session starting at tick `start`: baseline starts there, then n ticks. Returns
    per-tick (score, level). Mirrors home_page._tickSecond: update only when gated, then compute."""
    det = StressDetector(60, 1, 12)
    det.start_baseline()
    out = []
    for t in range(start, min(start + n, len(ts.hr))):
        if ts.gate[t]:
            det.update(ts.hr[t], ts.hrv[t])
        out.append(det.compute())
    return out
