"""How much RMSSD error does the app's SQI filter remove, and how much data does it cost?

Dataset: PhysioNet Pulse Transit Time PPG Dataset v1.1.0 (see README.md).
Pipeline: analysis/app_pipeline.py (verified port of the app's Dart code).

Run from analysis/:  .venv/bin/python run_analysis.py
Outputs in results/: windows.csv, sweep.csv, summary.json, run_log.txt
"""
from __future__ import annotations

import json
import math
import platform
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
from scipy import stats

import app_pipeline as ap
from load_ptt import load, records, resample

HERE = Path(__file__).resolve().parent
OUT = HERE / "results"

SEED = 20260928
FS_APP = 100.0            # the glasses stream at 100 Hz (firmware + home_page.dart:18)
WIN_S = 60.0              # RMSSD window
START_S = 10.0            # skip filter/SQI warm-up at the start of each record
N_MIN_PPG = 10            # min accepted PPG intervals to compute a window RMSSD
N_MIN_ECG = 20            # min valid ECG RR intervals for the reference
RR_REF_MS = (300.0, 2000.0)
# window SQIs cluster in 0.8-1.0 on this data, so the grid is finer there
TAUS = np.unique(np.round(np.concatenate([np.arange(0.0, 0.8, 0.05), np.arange(0.8, 1.0001, 0.01)]), 2))
IN_LOOP_GATES = [0.2, 0.3, 0.4]
APP_TAU = 0.4
HIGH_TAUS = [0.96, 0.97, 0.98]
N_BOOT = 2000


# --------------------------------------------------------------------------- per window
def ecg_rmssd(r_s: np.ndarray, t0: float, t1: float):
    b = r_s[(r_s >= t0) & (r_s < t1)]
    rr = np.diff(b) * 1000.0
    ok = (rr >= RR_REF_MS[0]) & (rr <= RR_REF_MS[1])
    if ok.sum() < N_MIN_ECG:
        return math.nan, int(ok.sum()), math.nan
    pair = ok[1:] & ok[:-1]           # successive differences only between adjacent valid RR
    d = np.diff(rr)[pair]
    return float(np.sqrt(np.mean(d**2))), int(ok.sum()), float(60000.0 / np.median(rr[ok]))


def ppg_window(res: ap.SessionResult, fs: float, t0: float, t1: float):
    """RMSSD with the app's formula on the intervals the app accepted in [t0, t1)."""
    t = np.asarray(res.accepted_end_packet) / fs
    iv = np.asarray(res.accepted_intervals_ms)[(t >= t0) & (t < t1)]
    if len(iv) < N_MIN_PPG:
        return math.nan, len(iv)
    return ap.compute_rmssd(list(iv)), len(iv)


def tick_frame(res: ap.SessionResult, fs: float) -> pd.DataFrame:
    df = pd.DataFrame(res.ticks)
    df["t"] = (df["sample"] + 1) / fs
    early = df["reject"].isin(["warmup", "presence", "flat"])
    df["sqi_full"] = df["sqi"]
    # ablation: each component alone, keeping the checks that belong to it
    df["sqi_amp"] = np.where(early | (df["reject"] == "zombie"), 0.0, df["mod_score"] * df["penalty"])
    df["sqi_per"] = np.where(early, 0.0, df["per"])
    return df


def process(name: str) -> list[dict]:
    rec = load(name)
    ir1 = resample(rec.ir1, rec.fs, FS_APP)
    ir2 = resample(rec.ir2, rec.fs, FS_APP)
    runs = {
        "off": ap.run_session(ir1, FS_APP, gate=None, record_per_sample=False, tick_parts=True),
        "sensor2_off": ap.run_session(ir2, FS_APP, gate=None, record_per_sample=False, tick_parts=True),
        # hypothetical variant NOT in the app: detector fed the inverted signal (systolic peaks)
        "inverted_off": ap.run_session(2 * np.median(ir1) - ir1, FS_APP, gate=None,
                                       record_per_sample=False, tick_parts=True),
    }
    for g in IN_LOOP_GATES:
        runs[f"inloop_{g}"] = ap.run_session(ir1, FS_APP, gate=g, record_per_sample=False)
    # v2 (not in the app): same pipeline, beats timed on the systolic peak
    runs["v2"] = ap.run_session(ir1, FS_APP, gate=None, record_per_sample=False, tick_parts=True, systolic=True)
    runs["v2_inloop_0.4"] = ap.run_session(ir1, FS_APP, gate=0.4, record_per_sample=False, systolic=True)
    ticks = {k: tick_frame(runs[k], FS_APP) for k in ("off", "sensor2_off", "inverted_off", "v2")}

    duration = len(rec.ir1) / rec.fs
    rows = []
    t0 = START_S
    while t0 + WIN_S <= duration + 1e-9:
        t1 = t0 + WIN_S
        ref, n_ref, hr_ref = ecg_rmssd(rec.r_peaks_s, t0, t1)
        i0, i1 = int(t0 * rec.fs), int(t1 * rec.fs)
        row = dict(record=name, subject=rec.subject, activity=rec.activity, t0=t0,
                   ref_rmssd=ref, ref_n=n_ref, ref_hr=hr_ref,
                   acc_sd=float(np.std(rec.acc_mag[i0:i1])))
        for k, res in runs.items():
            v, n = ppg_window(res, FS_APP, t0, t1)
            row[f"rmssd_{k}"], row[f"n_{k}"] = v, n
        for k, df in ticks.items():
            w = df[(df["t"] > t0) & (df["t"] <= t1)]
            for comp in ("sqi_full", "sqi_amp", "sqi_per"):
                row[f"{comp}_{k}"] = float(w[comp].median())
            row[f"mod_median_{k}"] = float(w["mod"].median())
            row[f"penalty_lt1_frac_{k}"] = float((w["penalty"] < 1).mean())
        rows.append(row)
        t0 = t1
    for r in rows:
        r["n_nan_samples"] = rec.n_nan
    return rows


# --------------------------------------------------------------------------- metrics
def metrics(err: np.ndarray, ppg: np.ndarray, ref: np.ndarray) -> dict:
    n = len(err)
    if n < 3:
        return dict(n=n)
    bias, sd = float(np.mean(err)), float(np.std(err, ddof=1))
    return dict(
        n=n,
        median_abs_err=float(np.median(np.abs(err))),
        mean_abs_err=float(np.mean(np.abs(err))),
        median_abs_pct_err=float(np.median(np.abs(err) / ref) * 100),
        pearson_r=float(stats.pearsonr(ppg, ref)[0]),
        spearman_rho=float(stats.spearmanr(ppg, ref)[0]),
        ba_bias=bias, ba_loa_low=bias - 1.96 * sd, ba_loa_high=bias + 1.96 * sd,
    )


def kept_mask(df, run, comp, tau):
    ok = df[f"rmssd_{run}"].notna()
    if comp is None or tau <= 0:
        return ok
    return ok & (df[f"{comp}_{run}"] >= tau)


def sweep(df: pd.DataFrame) -> pd.DataFrame:
    total = len(df)
    out = []
    for run in ("off", "sensor2_off", "inverted_off", "v2"):
        for comp in ("sqi_full", "sqi_amp", "sqi_per"):
            for tau in TAUS:
                m = kept_mask(df, run, comp, tau)
                d = df[m]
                err = (d[f"rmssd_{run}"] - d["ref_rmssd"]).to_numpy()
                row = dict(run=run, variant=comp, tau=float(tau), coverage=m.sum() / total,
                           n_subjects=d["subject"].nunique())
                row.update(metrics(err, d[f"rmssd_{run}"].to_numpy(), d["ref_rmssd"].to_numpy()))
                out.append(row)
    return pd.DataFrame(out)


def boot_median_ae(df, masks: dict, rng) -> dict:
    """Cluster bootstrap over subjects: 95% CI of median |error| and of differences vs 'none'."""
    subjects = df["subject"].unique()
    by_subj = {s: np.flatnonzero(df["subject"].to_numpy() == s) for s in subjects}
    ae = {k: np.abs(v[0] - df["ref_rmssd"].to_numpy()) for k, v in masks.items()}
    keep = {k: v[1].to_numpy() for k, v in masks.items()}
    samples = {k: [] for k in masks}
    for _ in range(N_BOOT):
        idx = np.concatenate([by_subj[s] for s in rng.choice(subjects, len(subjects), replace=True)])
        for k in masks:
            sel = idx[keep[k][idx]]
            samples[k].append(np.median(ae[k][sel]) if len(sel) else np.nan)
    out = {}
    for k, v in samples.items():
        v = np.asarray(v)
        out[k] = dict(ci95=[float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))])
        if k != "none":
            dv = np.asarray(samples["none"]) - v
            out[k]["reduction_vs_none_ci95"] = [float(np.nanpercentile(dv, 2.5)), float(np.nanpercentile(dv, 97.5))]
    return out


def main():
    t_start = time.time()
    OUT.mkdir(exist_ok=True)
    names = records()
    with Pool() as pool:
        rows = [r for rs in pool.map(process, names) for r in rs]
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "windows.csv", index=False)

    n_all = len(df)
    df = df[df["ref_rmssd"].notna()].reset_index(drop=True)   # windows with a valid ECG reference
    sw = sweep(df)
    sw.to_csv(OUT / "sweep.csv", index=False)

    def pick(run, comp, tau):
        r = sw[(sw.run == run) & (sw.variant == comp) & np.isclose(sw.tau, tau)].iloc[0]
        return {k: (None if (isinstance(v, float) and math.isnan(v)) else v) for k, v in r.to_dict().items()}

    total = len(df)
    summary = dict(
        dataset="PhysioNet Pulse Transit Time PPG Dataset v1.1.0 (22 subjects, sit/walk/run, finger MAX30101 IR)",
        windows_total=n_all, windows_with_ecg_reference=total,
        subjects=int(df["subject"].nunique()),
        params=dict(fs_app=FS_APP, win_s=WIN_S, start_s=START_S, n_min_ppg=N_MIN_PPG,
                    n_min_ecg=N_MIN_ECG, rr_ref_ms=RR_REF_MS, window_sqi="median of 1 Hz SQI ticks",
                    seed=SEED, n_boot=N_BOOT),
        no_filter=pick("off", "sqi_full", 0.0),
        post_hoc_app_threshold={c: pick("off", c, APP_TAU) for c in ("sqi_full", "sqi_amp", "sqi_per")},
    )

    # the app as deployed: SQI gate inside the loop (goodQuality at every beat)
    inloop = {}
    for g in IN_LOOP_GATES:
        m = df[f"rmssd_inloop_{g}"].notna()
        d = df[m]
        err = (d[f"rmssd_inloop_{g}"] - d["ref_rmssd"]).to_numpy()
        inloop[str(g)] = dict(coverage=float(m.sum() / total), **metrics(err, d[f"rmssd_inloop_{g}"].to_numpy(), d["ref_rmssd"].to_numpy()))
    summary["in_loop_gate_as_app"] = inloop

    # motion (accelerometer) gate at the same coverage as the post-hoc full SQI >= 0.4
    m_sqi = kept_mask(df, "off", "sqi_full", APP_TAU)
    k = int(m_sqi.sum())
    comp_ok = df[df["rmssd_off"].notna()].sort_values("acc_sd")
    m_acc = df.index.isin(comp_ok.index[:k])
    d = df[m_acc]
    err = (d["rmssd_off"] - d["ref_rmssd"]).to_numpy()
    summary["motion_gate_same_coverage"] = dict(coverage=float(m_acc.sum() / total),
                                                acc_sd_cutoff_g=float(comp_ok["acc_sd"].iloc[k - 1]) if k else None,
                                                **metrics(err, d["rmssd_off"].to_numpy(), d["ref_rmssd"].to_numpy()))

    # High thresholds where the SQI starts to act on this data. NOTE: these values were
    # chosen after looking at the sweep (descriptive, not a tuned/validated operating point).
    high = {}
    comp_ok = df[df["rmssd_off"].notna()].sort_values("acc_sd")
    for tau in HIGH_TAUS:
        m = kept_mask(df, "off", "sqi_full", tau)
        d = df[m]
        k = int(m.sum())
        m_mot = df.index.isin(comp_ok.index[:k])
        dm = df[m_mot]
        e_m = (dm["rmssd_off"] - dm["ref_rmssd"]).to_numpy()
        high[str(tau)] = dict(
            coverage=float(m.sum() / total),
            n_windows=k, n_subjects=int(d["subject"].nunique()),
            median_abs_err=float(np.median(np.abs(d["rmssd_off"] - d["ref_rmssd"]))),
            activity_mix={a: int(v) for a, v in d["activity"].value_counts().items()},
            ref_rmssd_median_kept=float(d["ref_rmssd"].median()),
            ref_rmssd_median_dropped=float(df.loc[~m & df["rmssd_off"].notna(), "ref_rmssd"].median()),
            ppg_rmssd_median_kept=float(d["rmssd_off"].median()),
            motion_gate_same_coverage=dict(median_abs_err=float(np.median(np.abs(e_m))),
                                           activity_mix={a: int(v) for a, v in dm["activity"].value_counts().items()}),
        )
    summary["high_threshold_post_hoc"] = high

    # per activity
    per_act = {}
    for act, g in df.groupby("activity"):
        res = {}
        for label, mask, col in (
                ("none", kept_mask(g, "off", None, 0), "rmssd_off"),
                ("sqi_full>=0.4", kept_mask(g, "off", "sqi_full", APP_TAU), "rmssd_off"),
                ("in_loop_0.4", g["rmssd_inloop_0.4"].notna(), "rmssd_inloop_0.4"),
                ("inverted_input_none (not the app)", kept_mask(g, "inverted_off", None, 0), "rmssd_inverted_off")):
            dd = g[mask]
            e = (dd[col] - dd["ref_rmssd"]).to_numpy()
            res[label] = dict(coverage=float(mask.sum() / len(g)), **metrics(e, dd[col].to_numpy(), dd["ref_rmssd"].to_numpy()))
        res["windows"] = int(len(g))
        res["median_modulation_index"] = float(g["mod_median_off"].median())
        res["frac_ticks_with_artifact_penalty"] = float(g["penalty_lt1_frac_off"].mean())
        per_act[act] = res
    summary["per_activity"] = per_act

    # bootstrap CIs (subject-level) for the headline comparisons
    rng = np.random.default_rng(SEED)
    masks = {
        "none": (df["rmssd_off"].to_numpy(), kept_mask(df, "off", None, 0)),
        "sqi_full>=0.4": (df["rmssd_off"].to_numpy(), kept_mask(df, "off", "sqi_full", APP_TAU)),
        "in_loop_0.4": (df["rmssd_inloop_0.4"].to_numpy(), df["rmssd_inloop_0.4"].notna()),
        "motion_same_cov": (df["rmssd_off"].to_numpy(), pd.Series(m_acc)),
        "inverted_input_none (not the app)": (df["rmssd_inverted_off"].to_numpy(), kept_mask(df, "inverted_off", None, 0)),
        "v2_none (not the app)": (df["rmssd_v2"].to_numpy(), kept_mask(df, "v2", None, 0)),
    }
    for tau in HIGH_TAUS:
        masks[f"sqi_full>={tau} (post hoc)"] = (df["rmssd_off"].to_numpy(), kept_mask(df, "off", "sqi_full", tau))
    summary["bootstrap_median_abs_err"] = boot_median_ae(df, masks, rng)

    # robustness: computability threshold and polarity / second sensor
    summary["robustness"] = {
        "sensor2_no_filter": pick("sensor2_off", "sqi_full", 0.0),
        "sensor2_sqi_full_0.4": pick("sensor2_off", "sqi_full", APP_TAU),
        "inverted_input_no_filter (not the app)": pick("inverted_off", "sqi_full", 0.0),
        "inverted_input_sqi_full_0.4 (not the app)": pick("inverted_off", "sqi_full", APP_TAU),
    }
    summary["ref_rmssd_ms"] = dict(median=float(df["ref_rmssd"].median()),
                                   iqr=[float(df["ref_rmssd"].quantile(0.25)), float(df["ref_rmssd"].quantile(0.75))])
    summary["v2_no_filter (not the app)"] = pick("v2", "sqi_full", 0.0)
    m = df["rmssd_v2_inloop_0.4"].notna()
    d = df[m]
    summary["v2_in_loop_0.4 (not the app)"] = dict(coverage=float(m.sum() / total), **metrics(
        (d["rmssd_v2_inloop_0.4"] - d["ref_rmssd"]).to_numpy(), d["rmssd_v2_inloop_0.4"].to_numpy(), d["ref_rmssd"].to_numpy()))
    summary["n_nan_ppg_samples_total"] = int(df.drop_duplicates("record")["n_nan_samples"].sum())

    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    log = [f"run_analysis.py finished {time.strftime('%Y-%m-%d %H:%M:%S')}",
           f"elapsed_s={time.time() - t_start:.1f}", f"python={sys.version.split()[0]} {platform.platform()}",
           f"numpy={np.__version__} scipy={scipy.__version__} pandas={pd.__version__}",
           f"records={len(names)} windows_total={n_all} windows_with_ref={total}", f"seed={SEED}"]
    (OUT / "run_log.txt").write_text("\n".join(log) + "\n")
    print("\n".join(log))


if __name__ == "__main__":
    main()
