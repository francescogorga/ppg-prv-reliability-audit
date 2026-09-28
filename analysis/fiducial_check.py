"""Where do the app's PPG peaks fall relative to the ECG R peak?

For every record: timing of each detected PPG peak after the preceding R peak, for the
signal as the app receives it (raw light polarity) and for the inverted signal
(systolic peak, hypothetical). Writes results/fiducial_check.csv and .json.
"""
import json
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

import app_pipeline as ap
from load_ptt import load, records, resample

RES = Path(__file__).resolve().parent / "results"
FS = 100.0


def one(name):
    rec = load(name)
    ir = resample(rec.ir1, rec.fs, FS)
    R = rec.r_peaks_s
    out = []
    for label, x in (("raw_as_app", ir), ("inverted", 2 * np.median(ir) - ir)):
        r = ap.run_session(x, FS, gate=None, record_per_sample=True)
        pk = np.flatnonzero(r.peak) / FS - 1 / FS   # the detector flags the previous sample
        j = np.searchsorted(R, pk) - 1
        ok = (j >= 0) & (pk >= 10.0)
        lag = (pk[ok] - R[j[ok]]) * 1000
        cnt = np.bincount(j[ok], minlength=len(R))[R >= 10.0]
        q25, q75 = np.percentile(lag, [25, 75])
        out.append(dict(record=name, activity=rec.activity, polarity=label, n_r=int(len(cnt)),
                        lag_median_ms=float(np.median(lag)), lag_iqr_ms=float(q75 - q25),
                        beats_missed_pct=float((cnt == 0).mean() * 100),
                        beats_multi_pct=float((cnt >= 2).mean() * 100)))
    return out


def main():
    RES.mkdir(exist_ok=True)
    with Pool() as p:
        df = pd.DataFrame([r for rs in p.map(one, records()) for r in rs])
    df.to_csv(RES / "fiducial_check.csv", index=False)
    summ = {}
    for (pol, act), g in df.groupby(["polarity", "activity"]):
        summ.setdefault(pol, {})[act] = {c: float(g[c].median()) for c in
                                          ("lag_median_ms", "lag_iqr_ms", "beats_missed_pct", "beats_multi_pct")}
    for pol, g in df.groupby("polarity"):
        summ[pol]["all"] = {c: float(g[c].median()) for c in
                            ("lag_median_ms", "lag_iqr_ms", "beats_missed_pct", "beats_multi_pct")}
    summ["note"] = "medians across records of per-record statistics; beats counted from t >= 10 s"
    (RES / "fiducial_check.json").write_text(json.dumps(summ, indent=2))
    print(json.dumps(summ, indent=2))


if __name__ == "__main__":
    main()
