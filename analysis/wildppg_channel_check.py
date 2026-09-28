"""Is the forehead failure the channel or the algorithm? (WildPPG, run after run_wildppg.py)

1. Does the channel carry the heartbeat? In the quietest 20% of windows (head
   accelerometer SD), compare the spectral peak of the PPG (0.6-3 Hz, Welch, 16 s
   segments) with the ECG heart rate. Independent of the app's beat detector.
2. Best case for the app's detector at the head: green channel, systolic-peak
   polarity (as stored), all windows and quietest 20%.
Output: results/wildppg_channel_check.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal

import app_pipeline as ap
from load_wildppg import load
from run_analysis import ppg_window
from run_wildppg import MAX_REF_REJECT

RES = Path(__file__).resolve().parent / "results"
QUIET_Q = 0.2


def main():
    w = pd.read_csv(RES / "wildppg_windows.csv")
    w = w[w["ref_rmssd"].notna() & (w["ref_reject_frac"] <= MAX_REF_REJECT)]
    out = {}
    for pid, g in w.groupby("subject"):
        p = load(pid)
        fs = p.fs
        q = g["acc_sd"].quantile(QUIET_Q)
        quiet = g[g["acc_sd"] <= q]
        spec = {"ir": [], "green": []}
        for _, r in quiet.iterrows():
            i0, i1 = int(r.t0 * fs), int((r.t0 + 60) * fs)
            for name, x in (("ir", p.ir), ("green", p.green)):
                f, P = signal.welch(signal.detrend(x[i0:i1]), fs=fs, nperseg=int(16 * fs))
                band = (f > 0.6) & (f < 3.0)
                spec[name].append(abs(f[band][np.argmax(P[band])] * 60 - r.ref_hr))
        s = ap.run_session(p.green, fs, gate=None, record_per_sample=False)
        gs = np.array([ppg_window(s, fs, t0, t0 + 60)[0] for t0 in g["t0"]])
        err = np.abs(gs - g["ref_rmssd"].to_numpy())
        qmask = (g["acc_sd"] <= q).to_numpy()
        out[pid] = dict(
            quiet_windows=int(len(quiet)), quiet_acc_sd_max_g=float(q),
            spectral_hr_abs_err_bpm_median={k: float(np.median(v)) for k, v in spec.items()},
            spectral_hr_within_5bpm_pct={k: float(np.mean(np.array(v) < 5) * 100) for k, v in spec.items()},
            green_systolic_rmssd_abs_err_ms_median_all=float(np.nanmedian(err)),
            green_systolic_coverage_all=float(np.mean(np.isfinite(gs))),
            green_systolic_rmssd_abs_err_ms_median_quiet=float(np.nanmedian(err[qmask])),
            app_ir_rmssd_abs_err_ms_median_quiet=float((quiet["rmssd_app"] - quiet["ref_rmssd"]).abs().median()),
            ref_rmssd_median_quiet=float(quiet["ref_rmssd"].median()),
        )
    (RES / "wildppg_channel_check.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
