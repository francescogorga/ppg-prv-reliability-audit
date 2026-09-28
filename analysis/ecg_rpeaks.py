"""R-peak detector for datasets without manual annotations (WildPPG).

Pan-Tompkins-style: 5-20 Hz band-pass, squared derivative, 150 ms moving integration,
adaptive threshold (fraction of the local 98th percentile over 10 s, floored at 10% of the
recording's median level), 300 ms refractory.
Each detection is then moved to the extreme of the band-passed ECG within +-80 ms
(polarity chosen once per recording) and refined with parabolic interpolation, so
timing is not limited to the 1/fs grid.

Validated against the manually verified annotations of PhysioNet PTT-PPG after
resampling that ECG to 128 Hz (see validate_rpeaks.py).
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage, signal


def detect_r_peaks(ecg: np.ndarray, fs: float, thr_frac: float = 0.3) -> np.ndarray:
    """Returns R-peak times in seconds (float, sub-sample)."""
    x = np.asarray(ecg, dtype=float)
    x = x - np.median(x)
    b, a = signal.butter(2, [5.0, 20.0], btype="band", fs=fs)
    bp = signal.filtfilt(b, a, x)
    d = np.gradient(bp) ** 2
    win = max(1, int(round(0.150 * fs)))
    integ = np.convolve(d, np.ones(win) / win, mode="same")
    # local level: 98th percentile over 10 s, computed on 1 s blocks for speed
    blk = int(round(fs))
    n_blk = len(integ) // blk
    if n_blk == 0:
        return np.array([])
    p98 = np.array([np.percentile(integ[i * blk:(i + 1) * blk], 98) for i in range(n_blk)])
    level = ndimage.median_filter(p98, size=10, mode="nearest")
    # floor at 10% of the recording's typical level: avoids detections in noise-only
    # stretches (lead-off, flat segments, start of a recording)
    level = np.maximum(level, 0.1 * np.median(p98))
    level = np.repeat(level, blk)
    level = np.concatenate([level, np.full(len(integ) - len(level), level[-1])])
    cand, _ = signal.find_peaks(integ, height=thr_frac * level, distance=int(round(0.300 * fs)))
    if len(cand) == 0:
        return np.array([])
    half = int(round(0.080 * fs))
    # polarity of the QRS: sign of the larger excursion around candidates
    pos = np.median([bp[max(0, c - half):c + half].max() for c in cand])
    neg = np.median([-bp[max(0, c - half):c + half].min() for c in cand])
    y = bp if pos >= neg else -bp
    out = []
    for c in cand:
        lo, hi = max(1, c - half), min(len(y) - 1, c + half)
        k = lo + int(np.argmax(y[lo:hi]))
        k = min(max(k, 1), len(y) - 2)
        y0, y1, y2 = y[k - 1], y[k], y[k + 1]
        den = y0 - 2 * y1 + y2
        off = 0.5 * (y0 - y2) / den if den != 0 else 0.0
        out.append((k + float(np.clip(off, -0.5, 0.5))) / fs)
    t = np.unique(np.round(np.asarray(out), 6))
    # re-apply the refractory period after refinement
    keep = [0]
    for i in range(1, len(t)):
        if t[i] - t[keep[-1]] >= 0.300:
            keep.append(i)
    return t[keep]


def match(detected: np.ndarray, reference: np.ndarray, tol: float = 0.05):
    """Greedy matching within +-tol s. Returns (sensitivity, ppv, timing errors in s)."""
    j = np.searchsorted(detected, reference)
    errs, hit = [], np.zeros(len(detected), bool)
    for r, k in zip(reference, j):
        best = None
        for kk in (k - 1, k):
            if 0 <= kk < len(detected) and not hit[kk] and abs(detected[kk] - r) <= tol:
                if best is None or abs(detected[kk] - r) < abs(detected[best] - r):
                    best = kk
        if best is not None:
            hit[best] = True
            errs.append(detected[best] - r)
    tp = len(errs)
    se = tp / len(reference) if len(reference) else float("nan")
    ppv = tp / len(detected) if len(detected) else float("nan")
    return se, ppv, np.asarray(errs)


def rmssd_clean(r_s: np.ndarray, t0: float, t1: float, rr_range=(300.0, 2000.0),
                rel_tol: float = 0.20, n_min: int = 20):
    """Reference RMSSD for automatically detected beats.

    An RR interval is valid if inside rr_range and within +-rel_tol of the median of
    the 11 surrounding intervals (a common rule against missed/extra beats). Successive
    differences are taken only between adjacent valid intervals.
    Returns (rmssd_ms, n_valid_rr, hr_bpm, frac_rr_rejected).
    """
    b = r_s[(r_s >= t0) & (r_s < t1)]
    rr = np.diff(b) * 1000.0
    if len(rr) < n_min:
        return float("nan"), int(len(rr)), float("nan"), float("nan")
    med = ndimage.median_filter(rr, size=11, mode="nearest")
    ok = (rr >= rr_range[0]) & (rr <= rr_range[1]) & (np.abs(rr - med) <= rel_tol * med)
    frac_rej = 1.0 - ok.mean()
    if ok.sum() < n_min:
        return float("nan"), int(ok.sum()), float("nan"), float(frac_rej)
    pair = ok[1:] & ok[:-1]
    d = np.diff(rr)[pair]
    if len(d) < n_min - 1:
        return float("nan"), int(ok.sum()), float("nan"), float(frac_rej)
    return float(np.sqrt(np.mean(d ** 2))), int(ok.sum()), float(60000.0 / np.median(rr[ok])), float(frac_rej)
