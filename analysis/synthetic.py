"""Seeded synthetic PPG signals for testing the port. NOT real data."""
from __future__ import annotations

import numpy as np


def rr_series(n_beats: int, mean_ms: float, sd_ms: float, rng: np.random.Generator) -> np.ndarray:
    """AR(1) RR series so successive differences (RMSSD) are well defined."""
    rr = np.empty(n_beats)
    rr[0] = mean_ms
    phi = 0.5
    for k in range(1, n_beats):
        rr[k] = mean_ms + phi * (rr[k - 1] - mean_ms) + rng.normal(0, sd_ms * np.sqrt(1 - phi**2))
    return rr


def ppg_from_rr(rr_ms: np.ndarray, fs: float, dc: float, mod: float, noise_rel: float,
                rng: np.random.Generator, duration_s: float | None = None):
    """Reflectance-style raw IR: light DECREASES at systole, so raw = dc*(1 - mod*pulse)."""
    beat_t = np.cumsum(rr_ms) / 1000.0
    if duration_s is None:
        duration_s = beat_t[-1] + 1.0
    t = np.arange(int(duration_s * fs)) / fs
    pulse = np.zeros_like(t)
    for tb in beat_t:
        pulse += np.exp(-0.5 * ((t - tb - 0.12) / 0.06) ** 2)        # systolic
        pulse += 0.35 * np.exp(-0.5 * ((t - tb - 0.36) / 0.08) ** 2)  # diastolic wave
    raw = dc * (1.0 - mod * pulse) + rng.normal(0, noise_rel * dc * mod, size=t.size)
    return t, raw, beat_t[beat_t < duration_s]


def add_motion(raw: np.ndarray, fs: float, segments_s, amp_rel: float, rng: np.random.Generator):
    out = raw.copy()
    dc = float(np.median(raw))
    for (a, b) in segments_s:
        i0, i1 = int(a * fs), int(b * fs)
        n = i1 - i0
        tt = np.arange(n) / fs
        walk = np.cumsum(rng.normal(0, 1, n))
        walk = walk / (np.abs(walk).max() + 1e-12)
        out[i0:i1] += amp_rel * dc * (0.6 * np.sin(2 * np.pi * 2.1 * tt) + 0.4 * walk)
    return out


def make_cases(seed: int = 20260928):
    """Returns dict name -> (fs, raw_nA, true_beat_times_s, true_rr_ms)."""
    cases = {}
    rng = np.random.default_rng(seed)
    rr = rr_series(160, 820, 45, rng)
    _, raw, bt = ppg_from_rr(rr, 100.0, 50_000.0, 0.0006, 0.05, rng, duration_s=120)
    cases["clean_nose_100hz"] = (100.0, raw, bt, rr[: len(bt)])

    rng = np.random.default_rng(seed + 1)
    raw_m = add_motion(raw, 100.0, [(40, 55), (80, 90)], 0.02, rng)
    cases["motion_nose_100hz"] = (100.0, raw_m, bt, rr[: len(bt)])

    rng = np.random.default_rng(seed + 2)
    rr64 = rr_series(160, 760, 35, rng)
    _, raw64, bt64 = ppg_from_rr(rr64, 64.0, 30_000.0, 0.0008, 0.05, rng, duration_s=120)
    cases["clean_nose_64hz"] = (64.0, raw64, bt64, rr64[: len(bt64)])

    rng = np.random.default_rng(seed + 3)
    rr125 = rr_series(160, 900, 50, rng)
    _, raw125, bt125 = ppg_from_rr(rr125, 125.0, 70_000.0, 0.015, 0.05, rng, duration_s=120)
    cases["clean_finger_125hz"] = (125.0, raw125, bt125, rr125[: len(bt125)])

    raw_off = raw.copy()
    raw_off[int(60 * 100): int(80 * 100)] = 5.0 + np.random.default_rng(seed + 4).normal(0, 0.5, 2000)
    cases["sensor_off_100hz"] = (100.0, raw_off, bt, rr[: len(bt)])
    return cases
