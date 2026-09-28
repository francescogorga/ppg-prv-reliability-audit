"""Line-by-line Python port of the app's PPG pipeline (smart_wearables_app_stress/lib).

Source of truth (read-only, not modified):
  processing/ppg_processor.dart   BandPassFilter, PeakDetector, HeartRateTracker, PpgProcessor
  processing/sqi.dart             SignalQualityIndex
  processing/stress_detector.dart StressDetector.computeRmssd
  home_page.dart:151-199          order of operations per BLE packet (_onPacket)

The sampling rate is a parameter everywhere (the app hard-codes 100 Hz only in
home_page.dart:18). Arithmetic is kept in the same order as the Dart code so the
outputs match the Dart implementation to floating-point precision
(see tests/test_port.py and dart_ref/).
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field


def dart_round(x: float) -> int:
    """Dart's num.round(): half away from zero (Python's round() is half-to-even)."""
    return int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))


def _seq_sum(xs) -> float:
    # Plain left-to-right accumulation like the Dart loops. Python >= 3.12 sum()
    # uses compensated summation for floats, which would not match bit-for-bit.
    s = 0.0
    for v in xs:
        s += v
    return s


# --------------------------------------------------------------------------- filter
class Biquad:
    """Direct Form II Transposed biquad (ppg_processor.dart:3-21)."""

    __slots__ = ("b0", "b1", "b2", "a1", "a2", "z1", "z2")

    def __init__(self, b0, b1, b2, a1, a2):
        self.b0, self.b1, self.b2, self.a1, self.a2 = b0, b1, b2, a1, a2
        self.z1 = 0.0
        self.z2 = 0.0

    def process(self, x: float) -> float:
        y = self.b0 * x + self.z1
        self.z1 = self.b1 * x - self.a1 * y + self.z2
        self.z2 = self.b2 * x - self.a2 * y
        return y


SQRT1_2 = math.sqrt(0.5)  # Dart math.sqrt1_2


def make_highpass(fs: float, fc: float) -> Biquad:
    k = math.tan(math.pi * fc / fs)
    q = SQRT1_2
    norm = 1.0 / (1.0 + k / q + k * k)
    b0 = norm
    b1 = -2.0 * norm
    b2 = norm
    a1 = 2.0 * (k * k - 1.0) * norm
    a2 = (1.0 - k / q + k * k) * norm
    return Biquad(b0, b1, b2, a1, a2)


def make_lowpass(fs: float, fc: float) -> Biquad:
    k = math.tan(math.pi * fc / fs)
    q = SQRT1_2
    norm = 1.0 / (1.0 + k / q + k * k)
    b0 = k * k * norm
    b1 = 2.0 * b0
    b2 = b0
    a1 = 2.0 * (k * k - 1.0) * norm
    a2 = (1.0 - k / q + k * k) * norm
    return Biquad(b0, b1, b2, a1, a2)


class BandPassFilter:
    """2nd-order HP followed by 2nd-order LP (ppg_processor.dart:23-69)."""

    def __init__(self, fs: float, low_hz: float, high_hz: float):
        self.hp = make_highpass(fs, low_hz)
        self.lp = make_lowpass(fs, high_hz)

    def process(self, x: float) -> float:
        return self.lp.process(self.hp.process(x))


# --------------------------------------------------------------------------- peaks
class PeakDetector:
    """ppg_processor.dart:71-130."""

    def __init__(self, fs=100.0, refractory_ms=320, window_ms=2000, threshold_sigma=0.4):
        self.fs = fs
        self.refractory_samples = dart_round(fs * refractory_ms / 1000)
        self.window_size = dart_round(fs * window_ms / 1000)
        self.threshold_sigma = threshold_sigma
        self._window: deque[float] = deque()
        self._prev = 0.0
        self._prev_prev = 0.0
        self._since_last_peak = 1 << 30

    def process(self, x: float) -> bool:
        w = self._window
        w.append(x)
        if len(w) > self.window_size:
            w.popleft()
        self._since_last_peak += 1

        peak = False
        if (
            len(w) >= self.window_size // 2
            and self._since_last_peak >= self.refractory_samples
            and self._prev > self._prev_prev
            and self._prev > x
        ):
            n = len(w)
            mean = _seq_sum(w) / n
            var = 0.0
            for v in w:
                d = v - mean
                var += d * d
            var /= n
            threshold = mean + self.threshold_sigma * math.sqrt(var)
            if self._prev > threshold:
                peak = True
                self._since_last_peak = 0

        self._prev_prev = self._prev
        self._prev = x
        return peak


# --------------------------------------------------------------------------- HR / RR
class HeartRateTracker:
    """ppg_processor.dart:132-201."""

    def __init__(self, fs=100.0, max_intervals=60):
        self.fs = fs
        self.max_intervals = max_intervals
        self._peak_idx: deque[int] = deque()
        self.intervals_ms: list[float] = []
        self._counter = 0
        # analysis-only bookkeeping (not in Dart): sample index of the beat that
        # closed each accepted interval, and a log of every peak decision
        self.accepted_end_sample: list[int] = []

    def on_sample(self, peak: bool, good_quality: bool) -> tuple[float, bool] | None:
        """Returns (dt_ms, accepted) when a peak closes an interval, else None."""
        self._counter += 1
        if not peak:
            return None
        out = None
        if self._peak_idx:
            dt = (self._counter - self._peak_idx[-1]) / self.fs * 1000.0
            accepted = bool(good_quality and 300 < dt < 1500 and self._is_plausible_rr(dt))
            if accepted:
                self.intervals_ms.append(dt)
                self.accepted_end_sample.append(self._counter)
                if len(self.intervals_ms) > self.max_intervals:
                    self.intervals_ms.pop(0)
            out = (dt, accepted)
        self._peak_idx.append(self._counter)
        if len(self._peak_idx) > self.max_intervals + 1:
            self._peak_idx.popleft()
        return out

    def _is_plausible_rr(self, dt: float) -> bool:
        iv = self.intervals_ms
        if len(iv) < 3:
            return True
        recent = iv[-8:] if len(iv) > 8 else iv
        s = sorted(recent)
        median = s[len(s) // 2]
        return abs(dt - median) <= 0.30 * median

    @property
    def heart_rate_bpm(self) -> float | None:
        iv = self.intervals_ms
        if len(iv) < 3:
            return None
        hr_window = 10
        start = len(iv) - hr_window if len(iv) > hr_window else 0
        s = sorted(iv[start:])
        mid = len(s) // 2
        median = s[mid] if len(s) % 2 == 1 else (s[mid - 1] + s[mid]) / 2.0
        return 60000.0 / median


class PpgProcessor:
    """ppg_processor.dart:203-241 with the app's parameters."""

    AVG_WINDOW = 2

    def __init__(self, fs=100.0):
        self.fs = fs
        self.filter = BandPassFilter(fs, 0.5, 3.5)
        self.detector = PeakDetector(fs=fs, threshold_sigma=0.8, window_ms=4000, refractory_ms=400)
        self.hr = HeartRateTracker(fs=fs)
        self._avg: deque[float] = deque()
        self.last_filtered = 0.0
        self.last_peak = False

    def filter_and_detect(self, sample: float) -> bool:
        """First half of PpgProcessor.process: returns False if still filling the
        2-sample average (Dart returns early and does not touch the tracker)."""
        self._avg.append(sample)
        if len(self._avg) > self.AVG_WINDOW:
            self._avg.popleft()
        if len(self._avg) < self.AVG_WINDOW:
            return False
        smoothed = _seq_sum(self._avg) / self.AVG_WINDOW
        self.last_filtered = self.filter.process(smoothed)
        self.last_peak = self.detector.process(self.last_filtered)
        return True

    def process(self, sample: float, good_quality: bool):
        if self.filter_and_detect(sample):
            return self.hr.on_sample(self.last_peak, good_quality)
        return None


# --------------------------------------------------------------------------- SQI
@dataclass
class SqiParts:
    value: float
    modulation_index: float = float("nan")
    modulation_score: float = 0.0
    periodicity_score: float = 0.0
    artifact_penalty: float = 1.0
    early_reject: str = ""  # "", "warmup", "presence", "flat", "zombie"


def _saturate(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


class SignalQualityIndex:
    """sqi.dart:3-109. `parts()` also exposes the sub-scores for the ablation."""

    FULL_SCORE_MODULATION = 0.0002
    MIN_PRESENCE_DC = 10.0

    def __init__(self, fs=100.0, window_seconds=5):
        self.fs = fs
        self.window_size = dart_round(fs * window_seconds)
        self._filtered: deque[float] = deque()
        self._raw: deque[float] = deque()
        self._intervals: list[float] = []

    def push(self, filtered: float, raw: float):
        self._filtered.append(filtered)
        self._raw.append(raw)
        if len(self._filtered) > self.window_size:
            self._filtered.popleft()
            self._raw.popleft()

    def update_intervals(self, intervals_ms):
        self._intervals = list(intervals_ms)

    @property
    def value(self) -> float:
        return self.parts().value

    def parts(self) -> SqiParts:
        if len(self._filtered) < self.window_size // 2:
            return SqiParts(0.0, early_reject="warmup")
        dc = _seq_sum(self._raw) / len(self._raw)
        if dc < self.MIN_PRESENCE_DC:
            return SqiParts(0.0, early_reject="presence")
        raw_pp = max(self._raw) - min(self._raw)
        if raw_pp < 0.001:
            return SqiParts(0.0, early_reject="flat")
        ac_pp = max(self._filtered) - min(self._filtered)
        mod = ac_pp / dc
        mod_score = _saturate(mod / self.FULL_SCORE_MODULATION)
        per = self._periodicity_score()
        penalty = 1.0
        if mod > 0.03:
            penalty = 0.0
        elif mod > 0.02:
            penalty = 0.5
        if mod_score < 0.1:
            return SqiParts(0.0, mod, mod_score, per, penalty, early_reject="zombie")
        sqi = (0.40 * mod_score + 0.60 * per) * penalty
        return SqiParts(_saturate(sqi), mod, mod_score, per, penalty)

    def _periodicity_score(self) -> float:
        iv = self._intervals
        if len(iv) < 3:
            return 0.0
        mean = _seq_sum(iv) / len(iv)
        if mean <= 0:
            return 0.0
        var = 0.0
        for v in iv:
            d = v - mean
            var += d * d
        var /= len(iv)
        cv = math.sqrt(var) / mean
        return _saturate(1.0 - cv * 0.5)


def compute_rmssd(intervals_ms) -> float:
    """StressDetector.computeRmssd (stress_detector.dart:203-214)."""
    if len(intervals_ms) < 2:
        return 0.0
    s = 0.0
    n = 0
    for i in range(1, len(intervals_ms)):
        d = intervals_ms[i] - intervals_ms[i - 1]
        s += d * d
        n += 1
    return math.sqrt(s / n) if n else 0.0


# --------------------------------------------------------------------------- session
@dataclass
class SessionResult:
    fs: float
    n: int
    filtered: list[float] = field(default_factory=list)      # per sample (0 before first filter call)
    peak: list[bool] = field(default_factory=list)            # per sample
    sqi_after: list[float] = field(default_factory=list)      # per sample, SQI after this packet
    beats: list[tuple[int, float, bool, float]] = field(default_factory=list)
    # beats: (packet_index, dt_ms, accepted, sqi_used_for_gate) for every peak that closed an interval
    accepted_intervals_ms: list[float] = field(default_factory=list)
    accepted_end_packet: list[int] = field(default_factory=list)
    ticks: list[dict] = field(default_factory=list)            # 1 Hz snapshots like _tickSecond


def run_session(ir_na, fs=100.0, gate=0.4, warmup_samples=None, record_per_sample=True,
                tick_every=None, tick_parts=False, record_sqi=True) -> SessionResult:
    """Replays home_page.dart _onPacket for a stream of IR samples (already in nA).

    gate: SQI threshold used as `goodQuality` for RR acceptance (app: 0.4).
          gate=None disables SQI gating (goodQuality always true).
    warmup_samples: packets before SQI starts receiving data (app: 300 at 100 Hz,
          i.e. 3 s; scaled with fs when None).
    tick_every: samples between 1 Hz-style snapshots (default fs).
    """
    if warmup_samples is None:
        warmup_samples = dart_round(3.0 * fs)
    if tick_every is None:
        tick_every = dart_round(fs)
    ppg = PpgProcessor(fs)
    sqi = SignalQualityIndex(fs)
    res = SessionResult(fs=fs, n=len(ir_na))
    beats = res.beats
    warm = 0
    for i, x in enumerate(ir_na):
        warm += 1
        started = ppg.filter_and_detect(x)
        if started:
            if ppg.last_peak:
                # goodQuality is evaluated before this packet is pushed into the SQI
                # (home_page.dart:183). Only needed when a peak can close an interval.
                if gate is None:
                    q_val = float("nan")
                    good = True
                else:
                    q_val = sqi.value
                    good = q_val >= gate
                out = ppg.hr.on_sample(True, good)
                if out is not None:
                    beats.append((i, out[0], out[1], q_val))
            else:
                ppg.hr.on_sample(False, False)
        if warm > warmup_samples:
            sqi.push(ppg.last_filtered, x)
            sqi.update_intervals(ppg.hr.intervals_ms)
        if record_per_sample:
            res.filtered.append(ppg.last_filtered)
            res.peak.append(bool(started and ppg.last_peak))
            if record_sqi:  # O(window) per sample: skip it when only peaks are needed
                res.sqi_after.append(sqi.value)
        if (i + 1) % tick_every == 0:
            snap = {"sample": i, "sqi": sqi.value if not tick_parts else None,
                    "rmssd": compute_rmssd(ppg.hr.intervals_ms),
                    "hr": ppg.hr.heart_rate_bpm, "n_intervals": len(ppg.hr.intervals_ms)}
            if tick_parts:
                p = sqi.parts()
                snap.update(sqi=p.value, mod=p.modulation_index, mod_score=p.modulation_score,
                            per=p.periodicity_score, penalty=p.artifact_penalty, reject=p.early_reject)
            res.ticks.append(snap)
    # accepted intervals over the whole session, with the packet index closing them.
    # HeartRateTracker counts only packets after the first (2-sample average), so
    # its counter c corresponds to packet index c (0-based i = c).
    for (i, dt, acc, _q) in beats:
        if acc:
            res.accepted_intervals_ms.append(dt)
            res.accepted_end_packet.append(i)
    return res
