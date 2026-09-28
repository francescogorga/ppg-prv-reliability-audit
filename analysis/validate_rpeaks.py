"""Validates ecg_rpeaks.detect_r_peaks on PhysioNet PTT-PPG, whose R peaks were
verified manually, after resampling the ECG from 500 to 128 Hz (WildPPG's rate).

Reports beat-level sensitivity/PPV/timing error and, more importantly, the error
that the detector adds to a 60 s reference RMSSD. Output: results/rpeak_validation.json
"""
import json
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import wfdb
from scipy import signal

from ecg_rpeaks import detect_r_peaks, match, rmssd_clean
from load_ptt import DATA, records
from run_analysis import START_S, WIN_S, ecg_rmssd

RES = Path(__file__).resolve().parent / "results"
FS_OUT = 128.0


def one(name):
    rec = wfdb.rdrecord(str(DATA / name), channel_names=["ecg"])
    ann = wfdb.rdann(str(DATA / name), "atr")
    ref = ann.sample / rec.fs
    ecg = signal.resample_poly(rec.p_signal[:, 0], 32, 125)  # 500 -> 128 Hz
    det = detect_r_peaks(ecg, FS_OUT)
    se, ppv, err = match(det, ref)
    rows = []
    t0 = START_S
    dur = rec.sig_len / rec.fs
    while t0 + WIN_S <= dur + 1e-9:
        a, _, _ = ecg_rmssd(ref, t0, t0 + WIN_S)
        b, _, _ = ecg_rmssd(det, t0, t0 + WIN_S)
        c = rmssd_clean(ref, t0, t0 + WIN_S)[0]
        e = rmssd_clean(det, t0, t0 + WIN_S)[0]
        rows.append((a, b, c, e))
        t0 += WIN_S
    return dict(record=name, activity=name.split("_")[1], se=se, ppv=ppv,
                abs_err_ms=list(np.abs(err) * 1000), rmssd_pairs=rows)


def main():
    with Pool() as p:
        out = p.map(one, records())
    err = np.concatenate([o["abs_err_ms"] for o in out])
    pairs = np.array([r for o in out for r in o["rmssd_pairs"]], dtype=float)
    ok = ~np.isnan(pairs[:, :2]).any(axis=1)
    d = np.abs(pairs[ok, 1] - pairs[ok, 0])
    okc = ~np.isnan(pairs[:, [0, 3]]).any(axis=1)
    dc = np.abs(pairs[okc, 3] - pairs[okc, 0])     # detected+cleaned vs manual (as used for PTT)
    okcc = ~np.isnan(pairs[:, [2, 3]]).any(axis=1)
    dcc = np.abs(pairs[okcc, 3] - pairs[okcc, 2])  # both cleaned
    summ = dict(
        note="detector on PTT-PPG ECG resampled to 128 Hz vs manually verified R peaks (tolerance 50 ms)",
        records=len(out),
        sensitivity_median=float(np.median([o["se"] for o in out])),
        sensitivity_min=float(np.min([o["se"] for o in out])),
        ppv_median=float(np.median([o["ppv"] for o in out])),
        ppv_min=float(np.min([o["ppv"] for o in out])),
        timing_abs_err_ms_median=float(np.median(err)),
        timing_abs_err_ms_p95=float(np.percentile(err, 95)),
        rmssd_windows=int(ok.sum()),
        rmssd_abs_diff_ms_median=float(np.median(d)),
        rmssd_abs_diff_ms_p90=float(np.percentile(d, 90)),
        rmssd_ref_median_ms=float(np.median(pairs[ok, 0])),
        cleaned_detected_vs_manual=dict(windows=int(okc.sum()), abs_diff_ms_median=float(np.median(dc)),
                                        abs_diff_ms_p90=float(np.percentile(dc, 90)),
                                        abs_diff_ms_p99=float(np.percentile(dc, 99))),
        cleaned_detected_vs_cleaned_manual=dict(windows=int(okcc.sum()), abs_diff_ms_median=float(np.median(dcc)),
                                                abs_diff_ms_p90=float(np.percentile(dcc, 90))),
        per_activity={a: dict(se_median=float(np.median([o["se"] for o in out if o["activity"] == a])),
                              ppv_median=float(np.median([o["ppv"] for o in out if o["activity"] == a])))
                      for a in ("sit", "walk", "run")},
    )
    RES.mkdir(exist_ok=True)
    (RES / "rpeak_validation.json").write_text(json.dumps(summ, indent=2))
    print(json.dumps(summ, indent=2))


if __name__ == "__main__":
    main()
