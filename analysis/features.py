"""Per-window features for PPG quality estimation. None of them uses the ECG.

Input: a v2 session (app_pipeline.run_session with systolic=True, record_per_sample=True,
record_sqi=False, tick_parts=True), the raw PPG, the accelerometer magnitude and the window.
The ECG is used only outside this module, to build the label (RMSSD error).
"""
from __future__ import annotations

import math

import numpy as np
from scipy import signal, stats

import app_pipeline as ap

TEMPLATE_S = (-0.25, 0.45)   # beat segment around the detected (systolic) peak
FEATURES = [
    # app SQI and its parts (median of the 1 Hz values)
    "sqi_full", "sqi_amp", "sqi_per", "mod_index", "penalty_frac",
    # beat level (from the v2 detector)
    "n_peaks", "n_accepted", "reject_frac", "miss_frac_est", "hr_ppg", "rr_cv", "rr_diff_mad_rel",
    "rr_diff_max_rel", "ppg_rmssd", "tmpl_corr_mean", "tmpl_corr_p10", "tmpl_frac_lt08",
    # waveform
    "skewness", "kurtosis", "spec_purity", "spec_hr_mismatch",
    # accelerometer
    "acc_sd", "acc_p2p", "acc_hf_power",
]


def _nan_features():
    return {k: math.nan for k in FEATURES}


def window_features(res: ap.SessionResult, fs: float, filtered: np.ndarray, peaks: np.ndarray,
                    ticks, acc: np.ndarray, acc_fs: float, t0: float, t1: float) -> dict:
    f = _nan_features()
    i0, i1 = int(round(t0 * fs)), int(round(t1 * fs))
    x = -filtered[i0:i1]                           # volume polarity (v2 detects on the negated signal)
    # --- SQI parts
    w = ticks[(ticks["t"] > t0) & (ticks["t"] <= t1)]
    if len(w):
        f["sqi_full"] = float(w["sqi_full"].median())
        f["sqi_amp"] = float(w["sqi_amp"].median())
        f["sqi_per"] = float(w["sqi_per"].median())
        f["mod_index"] = float(w["mod"].median())
        f["penalty_frac"] = float((w["penalty"] < 1).mean())
    # --- beats
    pk = peaks[(peaks >= i0) & (peaks < i1)]
    f["n_peaks"] = float(len(pk))
    t_acc = np.asarray(res.accepted_end_packet) / fs
    iv = np.asarray(res.accepted_intervals_ms)[(t_acc >= t0) & (t_acc < t1)]
    f["n_accepted"] = float(len(iv))
    f["reject_frac"] = float(1 - len(iv) / max(len(pk) - 1, 1)) if len(pk) > 1 else 1.0
    if len(iv) >= 3:
        med = float(np.median(iv))
        f["hr_ppg"] = 60000.0 / med
        f["miss_frac_est"] = float(np.clip(1 - len(pk) / ((t1 - t0) * 1000.0 / med), -1, 1))
        f["rr_cv"] = float(np.std(iv) / np.mean(iv))
        d = np.abs(np.diff(iv))
        f["rr_diff_mad_rel"] = float(np.median(d) / med)
        f["rr_diff_max_rel"] = float(np.max(d) / med)
        f["ppg_rmssd"] = ap.compute_rmssd(list(iv))
    # --- beat template correlation
    a, b = int(round(TEMPLATE_S[0] * fs)), int(round(TEMPLATE_S[1] * fs))
    segs = [x[p - i0 + a: p - i0 + b] for p in pk if p - i0 + a >= 0 and p - i0 + b <= len(x)]
    if len(segs) >= 5:
        S = np.asarray(segs)
        S = S - S.mean(axis=1, keepdims=True)
        tmpl = np.median(S, axis=0)
        num = S @ tmpl
        den = np.linalg.norm(S, axis=1) * np.linalg.norm(tmpl) + 1e-12
        c = num / den
        f["tmpl_corr_mean"] = float(np.mean(c))
        f["tmpl_corr_p10"] = float(np.percentile(c, 10))
        f["tmpl_frac_lt08"] = float(np.mean(c < 0.8))
    # --- waveform statistics
    if len(x) > fs * 10 and np.std(x) > 0:
        f["skewness"] = float(stats.skew(x))
        f["kurtosis"] = float(stats.kurtosis(x))
        fr, P = signal.welch(x, fs=fs, nperseg=int(8 * fs))
        band = (fr >= 0.5) & (fr <= 3.5)
        if P[band].sum() > 0:
            fp = fr[band][np.argmax(P[band])]
            near = band & (np.abs(fr - fp) <= 0.15)
            f["spec_purity"] = float(P[near].sum() / P[band].sum())
            if not math.isnan(f["hr_ppg"]):
                f["spec_hr_mismatch"] = float(abs(fp * 60 - f["hr_ppg"]))
    # --- accelerometer
    j0, j1 = int(round(t0 * acc_fs)), int(round(t1 * acc_fs))
    acc_w = acc[j0:j1]
    if len(acc_w) > acc_fs * 10:
        f["acc_sd"] = float(np.std(acc_w))
        f["acc_p2p"] = float(np.percentile(acc_w, 99) - np.percentile(acc_w, 1))
        fr, P = signal.welch(acc_w - acc_w.mean(), fs=acc_fs, nperseg=int(4 * acc_fs))
        f["acc_hf_power"] = float(np.log10(P[(fr >= 1) & (fr <= 5)].sum() + 1e-12))
    return f
