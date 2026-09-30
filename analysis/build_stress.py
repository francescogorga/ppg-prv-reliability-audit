"""Does HRV error reach the app's stress output? Replays the app's 1 Hz stress loop.

For every record, second by second (home_page._tickSecond):
  ecg      HR and RMSSD from the ECG, same definitions as the app (HR = 60000 / median of the
           last 10 RR; RMSSD over the last 60 RR, here only between consecutive clean RR).
           This is the ECG-based application output, not psychological stress ground truth.
  v1_app   the app as deployed: v1 pipeline, stress updated only when SQI >= 0.4
  v2       v2 pipeline (systolic peak), stress updated every second
  v2_sqi   v2 pipeline with the app's SQI >= 0.4 gate
Sessions: the 60 s baseline starts at the session start (as when the user presses
"Start Baseline"): finger = one session per record from t = 10 s; forehead = 30-minute
sessions from t = 10 s. Output, one row per 60 s window (same grid as the features):
score and level of each variant at the window end. results/stress_{finger,forehead}.csv
usage: python build_stress.py [finger|forehead|all]
"""
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage

import app_pipeline as ap
from ecg_rpeaks import detect_r_peaks
from run_analysis import START_S, WIN_S
from run_wildppg import invert
from stress import TickSeries, simulate

RES = Path(__file__).resolve().parent / "results"
SESSION_S = {"finger": None, "forehead": 1800}


def ppg_ticks_v2(x, fs):
    """v2 run once; returns (no gate, app SQI gate). The app updates the stress detector
    only when the SQI shown at the previous tick is >= 0.4 (initially 0)."""
    s = ap.run_session(x, fs, gate=None, record_per_sample=False, systolic=True)
    hr = [t["hr"] for t in s.ticks]
    hrv = [t["rmssd"] for t in s.ticks]
    sqi = [t["sqi"] for t in s.ticks]
    return (TickSeries(hr, hrv, [True] * len(hr)),
            TickSeries(hr, hrv, [False] + [q >= 0.4 for q in sqi[:-1]]))


def ppg_ticks_app_v1(x, fs):
    # as deployed: RR accepted only when SQI >= 0.4 (in the loop), stress gated by SQI
    s = ap.run_session(x, fs, gate=0.4, record_per_sample=False)
    hr = [t["hr"] for t in s.ticks]
    hrv = [t["rmssd"] for t in s.ticks]
    sqi = [t["sqi"] for t in s.ticks]
    return TickSeries(hr, hrv, [False] + [q >= 0.4 for q in sqi[:-1]])


def ecg_ticks(r_s, n_ticks):
    rr = np.diff(r_s) * 1000.0
    t_end = r_s[1:]
    med = ndimage.median_filter(rr, size=11, mode="nearest")
    ok = (rr >= 300) & (rr <= 2000) & (np.abs(rr - med) <= 0.2 * med)
    hr, hrv = [], []
    for k in range(n_ticks):
        T = k + 1.0                                   # tick k happens at (k+1) s
        j = np.searchsorted(t_end, T, side="right")
        idx = np.arange(max(0, j - 60), j)
        v = idx[ok[idx]]
        last10 = v[-10:]
        hr.append(float(60000.0 / np.median(rr[last10])) if len(last10) >= 3 else None)
        pair = idx[1:][ok[idx[1:]] & ok[idx[:-1]]] if len(idx) > 1 else np.array([], int)
        d = rr[pair] - rr[pair - 1]
        hrv.append(float(np.sqrt(np.mean(d ** 2))) if len(d) >= 1 else 0.0)
    return TickSeries(hr, hrv, [True] * n_ticks)


def run(pid, record, activity, fs, x, r_s, duration, session_s):
    v2, v2_sqi = ppg_ticks_v2(x, fs)
    series = {"ecg": None, "v1_app": ppg_ticks_app_v1(x, fs), "v2": v2, "v2_sqi": v2_sqi}
    n = len(series["v2"].hr)
    series["ecg"] = ecg_ticks(r_s, n)
    starts = [START_S] if session_s is None else list(np.arange(START_S, duration - 120, session_s))
    rows = []
    for si, s0 in enumerate(starts):
        s1 = duration if session_s is None else min(s0 + session_s, duration)
        k0 = int(round(s0)) - 1                       # tick index at time s0
        out = {v: simulate(ts, k0, int(s1 - s0)) for v, ts in series.items()}
        t0 = s0
        while t0 + WIN_S <= s1 + 1e-9:
            k = int(round(t0 + WIN_S)) - 1 - k0       # tick at the window end, relative to the session
            row = dict(subject=pid, record=record, activity=activity, session=si, t0=t0,
                       baseline_window=bool(abs(t0 - s0) < 1e-9))
            for v, o in out.items():
                if 0 <= k < len(o):
                    row[f"score_{v}"], row[f"level_{v}"] = o[k]
            rows.append(row)
            t0 += WIN_S
    return rows


def finger_record(name):
    from load_ptt import load, resample
    rec = load(name)
    x = resample(rec.ir1, rec.fs, 100.0)
    return run(rec.subject, name, rec.activity, 100.0, x, rec.r_peaks_s, len(rec.ir1) / rec.fs, None)


def forehead_participant(pid):
    from load_wildppg import load
    p = load(pid)
    R = detect_r_peaks(p.ecg, p.fs)
    return run(pid, pid, "daily_life", p.fs, invert(p.ir), R, len(p.ecg) / p.fs, SESSION_S["forehead"])


def main(which):
    if which in ("finger", "all"):
        from load_ptt import records
        with Pool(6) as pool:
            rows = [r for rs in pool.map(finger_record, records()) for r in rs]
        pd.DataFrame(rows).to_csv(RES / "stress_finger.csv", index=False)
        print("finger rows", len(rows))
    if which in ("forehead", "all"):
        from load_wildppg import participants
        with Pool(3, maxtasksperchild=1) as pool:
            rows = [r for rs in pool.map(forehead_participant, participants()) for r in rs]
        pd.DataFrame(rows).to_csv(RES / "stress_forehead.csv", index=False)
        print("forehead rows", len(rows))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
