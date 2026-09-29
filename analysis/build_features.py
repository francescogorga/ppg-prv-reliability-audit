"""Builds the per-window table used by the quality models (quality_models.py).

One row per 60 s window: features from features.py (no ECG), plus the label
(v2 RMSSD error vs ECG) and the v1 (app) RMSSD for context.
  finger:   PhysioNet PTT-PPG, all 66 records, manual R peaks
  forehead: WildPPG, every participant present in data/wildppg/, automatic R peaks
Output: results/features_finger.csv, results/features_forehead.csv

usage: python build_features.py [finger|forehead|all]
"""
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

import app_pipeline as ap
from ecg_rpeaks import detect_r_peaks, rmssd_clean
from features import FEATURES, window_features
from run_analysis import START_S, WIN_S, ecg_rmssd, ppg_window, tick_frame
from run_wildppg import MAX_REF_REJECT, invert

RES = Path(__file__).resolve().parent / "results"


def _rows(pid, record, activity, fs, x, acc, acc_fs, ref_fn, duration):
    v2 = ap.run_session(x, fs, gate=None, record_per_sample=True, record_sqi=False, tick_parts=True, systolic=True)
    v1 = ap.run_session(x, fs, gate=None, record_per_sample=False)
    filt = np.asarray(v2.filtered)
    peaks = np.flatnonzero(np.asarray(v2.peak)) - 1          # the detector flags the previous sample
    ticks = tick_frame(v2, fs)
    rows = []
    t0 = START_S
    while t0 + WIN_S <= duration + 1e-9:
        t1 = t0 + WIN_S
        ref, ref_ok = ref_fn(t0, t1)
        r2, n2 = ppg_window(v2, fs, t0, t1)
        r1, _ = ppg_window(v1, fs, t0, t1)
        row = dict(subject=pid, record=record, activity=activity, t0=t0, ref_rmssd=ref, ref_ok=ref_ok,
                   rmssd_v2=r2, rmssd_v1=r1, n_v2=n2)
        row.update(window_features(v2, fs, filt, peaks, ticks, acc, acc_fs, t0, t1))
        rows.append(row)
        t0 = t1
    return rows


def finger_record(name):
    from load_ptt import load, resample
    rec = load(name)
    x = resample(rec.ir1, rec.fs, 100.0)

    def ref_fn(t0, t1):
        v, _, _ = ecg_rmssd(rec.r_peaks_s, t0, t1)
        return v, bool(np.isfinite(v))
    return _rows(rec.subject, name, rec.activity, 100.0, x, rec.acc_mag, rec.fs, ref_fn, len(rec.ir1) / rec.fs)


def forehead_participant(pid):
    from load_wildppg import load
    p = load(pid)
    R = detect_r_peaks(p.ecg, p.fs)

    def ref_fn(t0, t1):
        v, _, _, rej = rmssd_clean(R, t0, t1)
        return v, bool(np.isfinite(v) and rej <= MAX_REF_REJECT)
    return _rows(pid, pid, "daily_life", p.fs, invert(p.ir), p.acc_mag, p.fs, ref_fn, len(p.ecg) / p.fs)


def main(which):
    RES.mkdir(exist_ok=True)
    if which in ("finger", "all"):
        from load_ptt import records
        with Pool(6) as pool:
            rows = [r for rs in pool.map(finger_record, records()) for r in rs]
        pd.DataFrame(rows).to_csv(RES / "features_finger.csv", index=False)
        print("finger windows:", len(rows))
    if which in ("forehead", "all"):
        from load_wildppg import participants
        pids = participants()
        with Pool(3, maxtasksperchild=1) as pool:     # ~1-1.5 GB RAM per participant
            rows = [r for rs in pool.map(forehead_participant, pids) for r in rs]
        pd.DataFrame(rows).to_csv(RES / "features_forehead.csv", index=False)
        print("forehead participants:", len(pids), "windows:", len(rows))
    assert all(k in FEATURES for k in FEATURES)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
