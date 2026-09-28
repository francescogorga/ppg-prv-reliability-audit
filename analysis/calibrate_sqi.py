"""Test 2: calibrate the gate threshold honestly and measure it on unseen people.

The threshold is never chosen on the data it is evaluated on.
- Finger (PTT-PPG, 22 subjects): 200 random splits into 11 calibration + 11 test
  subjects. On the calibration half, the threshold is set so that a target share of
  the windows is kept (75%, 50%, 25%). It is then applied unchanged to the test half.
- Forehead (WildPPG, 2 participants): calibrate on one, test on the other, both ways.
- Transfer: thresholds calibrated on all finger data, applied to the forehead.

Gates compared: app SQI, periodicity term only, accelerometer (least motion kept),
and the oracle at the same test coverage (ranked by true error; unreachable ceiling).
Main pipeline: v2 (beats timed on the systolic peak, not in the app); v1 (the app)
for comparison. Output: results/sqi_calibration.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from run_analysis import SEED
from run_wildppg import MAX_REF_REJECT

RES = Path(__file__).resolve().parent / "results"
TARGETS = (0.75, 0.50, 0.25)
N_SPLITS = 200

FINGER = {"v2": ("rmssd_v2", "sqi_full_v2", "sqi_per_v2"), "v1 (app)": ("rmssd_off", "sqi_full_off", "sqi_per_off")}
FOREHEAD = {"v2": ("rmssd_v2", "sqi_full_v2", "sqi_per_v2"), "v1 (app)": ("rmssd_app", "sqi_full_app", "sqi_per_app")}


def load(csv):
    df = pd.read_csv(RES / csv)
    df = df[df["ref_rmssd"].notna()]
    if "ref_reject_frac" in df:
        df = df[df["ref_reject_frac"] <= MAX_REF_REJECT]
    return df.reset_index(drop=True)


def gates(df, cols):
    rm, sqi, per = cols
    ok = df[rm].notna().to_numpy()
    ae = np.abs(df[rm] - df["ref_rmssd"]).to_numpy()
    # higher score = keep first
    return ok, ae, {"sqi_full": df[sqi].fillna(-1).to_numpy(),
                    "sqi_per": df[per].fillna(-1).to_numpy(),
                    "motion": -df["acc_sd"].to_numpy()}


def threshold(score, ok, target):
    """Score threshold keeping `target` of ALL windows (only computable ones can be kept)."""
    k = int(round(target * len(score)))
    s = np.sort(score[ok])[::-1]
    if k <= 0:
        return np.inf
    if k > len(s):
        return -np.inf
    return s[k - 1]


def evaluate(ok, ae, score, thr):
    keep = ok & (score >= thr)
    cov = keep.sum() / len(ok)
    return cov, (float(np.median(ae[keep])) if keep.sum() >= 5 else np.nan), keep


def oracle(ok, ae, cov):
    k = int(round(cov * len(ok)))
    v = np.sort(ae[ok])[:k]
    return float(np.median(v)) if k >= 5 else np.nan


def summarize(rows):
    df = pd.DataFrame(rows)
    out = {}
    for (gate, target), g in df.groupby(["gate", "target"]):
        q = lambda c: [float(np.nanpercentile(g[c], 2.5)), float(np.nanmedian(g[c])), float(np.nanpercentile(g[c], 97.5))]
        out[f"{gate}@{int(target * 100)}%"] = dict(
            test_coverage_pct=[x * 100 for x in q("cov")], test_median_abs_err_ms=q("mae"),
            test_no_gate_ms=q("base"), reduction_ms=q("red"), oracle_same_coverage_ms=q("orc"),
            note="[2.5th percentile, median, 97.5th percentile] across splits")
    return out


def main():
    rng = np.random.default_rng(SEED)
    result = {"method": __doc__.strip().splitlines()[0], "n_splits": N_SPLITS, "targets": TARGETS}

    fin = load("windows.csv")
    subjects = np.sort(fin["subject"].unique())
    splits = [rng.permutation(subjects) for _ in range(N_SPLITS)]
    result["finger_split_half"] = {}
    for run, cols in FINGER.items():
        ok, ae, sc = gates(fin, cols)
        rows = []
        for perm in splits:
            cal = fin["subject"].isin(perm[: len(perm) // 2]).to_numpy()
            tst = ~cal
            base = float(np.median(ae[tst & ok]))
            for gname, score in sc.items():
                for t in TARGETS:
                    thr = threshold(score[cal], ok[cal], t)
                    cov, mae, _ = evaluate(ok[tst], ae[tst], score[tst], thr)
                    rows.append(dict(gate=gname, target=t, cov=cov, mae=mae, base=base, red=base - mae,
                                     orc=oracle(ok[tst], ae[tst], cov)))
        result["finger_split_half"][run] = summarize(rows)

    fh = load("wildppg_windows.csv")
    result["forehead_leave_one_participant_out"] = {}
    for run, cols in FOREHEAD.items():
        ok, ae, sc = gates(fh, cols)
        res = {}
        for cal_p in fh["subject"].unique():
            cal = (fh["subject"] == cal_p).to_numpy()
            tst = ~cal
            base = float(np.median(ae[tst & ok]))
            for gname, score in sc.items():
                for t in TARGETS:
                    thr = threshold(score[cal], ok[cal], t)
                    cov, mae, _ = evaluate(ok[tst], ae[tst], score[tst], thr)
                    res[f"calibrate_{cal_p}->test_other | {gname}@{int(t * 100)}%"] = dict(
                        threshold=float(thr), test_coverage_pct=cov * 100, test_median_abs_err_ms=mae,
                        test_no_gate_ms=base, oracle_same_coverage_ms=oracle(ok[tst], ae[tst], cov))
        result["forehead_leave_one_participant_out"][run] = res

    # transfer: threshold calibrated on all finger windows, applied to the forehead (v2)
    okf, aef, scf = gates(fin, FINGER["v2"])
    okh, aeh, sch = gates(fh, FOREHEAD["v2"])
    tr = {}
    for gname in ("sqi_full", "sqi_per"):
        for t in TARGETS:
            thr = threshold(scf[gname], okf, t)
            cov, mae, _ = evaluate(okh, aeh, sch[gname], thr)
            tr[f"{gname}@{int(t * 100)}% (finger)"] = dict(threshold=float(thr), forehead_coverage_pct=cov * 100,
                                                          forehead_median_abs_err_ms=mae,
                                                          forehead_no_gate_ms=float(np.median(aeh[okh])))
    result["transfer_finger_to_forehead_v2"] = tr
    (RES / "sqi_calibration.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
