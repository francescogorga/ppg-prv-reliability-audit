"""Same question as run_analysis.py, at a head site: WildPPG forehead PPG (MAX86141).

Polarity. The app receives raw MAX30101 counts (light polarity: light drops at systole)
and detects maxima. WildPPG stores PPG in blood-volume polarity: the mean forehead
waveform peaks ~350 ms after the R wave, the green channel's steepest slope is the
upstroke, and the official WildPPG code feeds ppg_g.v unchanged to the ppg-beats
toolbox, which expects volume polarity (see results/wildppg_polarity.json). So:
  run "app"      = forehead IR inverted to light polarity  -> what the app would see
  run "systolic" = forehead IR as stored (maxima = systolic peaks) -> hypothetical variant
Robustness: green channel (light polarity), and the app run resampled to 100 Hz.

Reference: R peaks detected on the sternum Lead-I ECG (ecg_rpeaks.py, validated in
validate_rpeaks.py on PTT-PPG, not on annotated WildPPG ECG), RMSSD with a standard RR cleaning rule; windows whose ECG has
more than 10% rejected RR are excluded as unreliable reference.

The default is the original two-participant analysis (an0, e61), even when all
16 extracted recordings are available. Pass participant IDs to change that scope.

Run from analysis/: .venv/bin/python run_wildppg.py  -> results/wildppg_*.{csv,json}
"""
from __future__ import annotations

import json
import math
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal

import app_pipeline as ap
from ecg_rpeaks import detect_r_peaks, rmssd_clean
from load_wildppg import load, participants
from run_analysis import (APP_TAU, HIGH_TAUS, N_BOOT, N_MIN_PPG, SEED, START_S, TAUS, WIN_S,
                          metrics, ppg_window, tick_frame)

HERE = Path(__file__).resolve().parent
OUT = HERE / "results"
MAX_REF_REJECT = 0.10     # ECG reference windows with >10% rejected RR are excluded
BLOCK_S = 600             # bootstrap blocks of 10 min (serial correlation within a person)
TICK_RUNS = ("app", "systolic", "green", "v2")


def invert(x):
    return 2 * np.median(x) - x


def _run(args):
    pid, run = args
    p = load(pid)
    fs = p.fs
    if run == "app":
        x, f, gate, parts = invert(p.ir), fs, None, True
    elif run == "systolic":
        x, f, gate, parts = p.ir, fs, None, True
    elif run == "green":
        x, f, gate, parts = invert(p.green), fs, None, True
    elif run == "inloop_0.4":
        x, f, gate, parts = invert(p.ir), fs, 0.4, False
    elif run == "v2":  # not in the app: light-polarity input, beats timed on the systolic peak
        x, f, gate, parts = invert(p.ir), fs, None, True
    elif run == "v2_inloop_0.4":
        x, f, gate, parts = invert(p.ir), fs, 0.4, False
    elif run == "app_100hz":
        x, f, gate, parts = signal.resample_poly(invert(p.ir), 25, 32), 100.0, None, False
    else:
        raise ValueError(run)
    t = time.time()
    res = ap.run_session(x, f, gate=gate, record_per_sample=False, tick_parts=parts, systolic=run.startswith("v2"))
    return pid, run, res, f, time.time() - t


def main(pids=("an0", "e61")):
    t_start = time.time()
    OUT.mkdir(exist_ok=True)
    available = participants()
    missing = set(pids) - set(available)
    if missing:
        raise FileNotFoundError(f"Missing WildPPG participants {sorted(missing)}; run download_wildppg.sh first")
    runs = ["app", "systolic", "green", "inloop_0.4", "app_100hz", "v2", "v2_inloop_0.4"]
    with Pool() as pool:
        out = pool.map(_run, [(pid, r) for pid in pids for r in runs])
    res = {(pid, r): (s, f, el) for pid, r, s, f, el in out}

    rows, polarity, fid = [], {}, {}
    for pid in pids:
        p = load(pid)
        R = detect_r_peaks(p.ecg, p.fs)
        dur = len(p.ecg) / p.fs
        ticks = {r: tick_frame(res[(pid, r)][0], res[(pid, r)][1]) for r in TICK_RUNS}
        t0 = START_S
        while t0 + WIN_S <= dur + 1e-9:
            t1 = t0 + WIN_S
            ref, n_ref, hr_ref, rej = rmssd_clean(R, t0, t1)
            i0, i1 = int(t0 * p.fs), int(t1 * p.fs)
            row = dict(subject=pid, activity=pid, t0=t0, block=f"{pid}_{int(t0 // BLOCK_S)}",
                       ref_rmssd=ref, ref_n=n_ref, ref_hr=hr_ref, ref_reject_frac=rej,
                       acc_sd=float(np.std(p.acc_mag[i0:i1])))
            for r in runs:
                v, n = ppg_window(res[(pid, r)][0], res[(pid, r)][1], t0, t1)
                row[f"rmssd_{r}"], row[f"n_{r}"] = v, n
            for r, df in ticks.items():
                w = df[(df["t"] > t0) & (df["t"] <= t1)]
                for comp in ("sqi_full", "sqi_amp", "sqi_per"):
                    row[f"{comp}_{r}"] = float(w[comp].median())
                row[f"mod_median_{r}"] = float(w["mod"].median())
                row[f"penalty_lt1_frac_{r}"] = float((w["penalty"] < 1).mean())
            rows.append(row)
            t0 = t1

        # polarity evidence (first hour): mean waveform around R, and steepest-slope sign
        idx = (R[(R > 1) & (R < 3590)] * p.fs).astype(int)
        b, a = signal.butter(2, [0.5, 8], btype="band", fs=p.fs)
        pol = {}
        for name, sig in (("ir", p.ir), ("green", p.green)):
            fsig = signal.filtfilt(b, a, sig[: int(3600 * p.fs)])
            m = np.mean([fsig[i:i + int(p.fs)] for i in idx if i + int(p.fs) < len(fsig)], axis=0)
            d = np.diff(m)
            pol[name] = dict(max_after_R_ms=float(np.argmax(m) / p.fs * 1000),
                             min_after_R_ms=float(np.argmin(m) / p.fs * 1000),
                             steepest_pos_over_neg_slope=float(d.max() / abs(d.min())))
        polarity[pid] = pol

        # where the detected peaks fall relative to R (as in fiducial_check.py)
        fid[pid] = {}
        for r in ("app", "systolic"):
            s = ap.run_session(invert(p.ir) if r == "app" else p.ir, p.fs, gate=None, record_per_sample=True,
                               record_sqi=False)
            pk = np.flatnonzero(s.peak) / p.fs - 1 / p.fs
            j = np.searchsorted(R, pk) - 1
            ok = (j >= 0) & (pk >= START_S)
            lag = (pk[ok] - R[j[ok]]) * 1000
            cnt = np.bincount(j[ok], minlength=len(R))[R >= START_S]
            q25, q75 = np.percentile(lag, [25, 75])
            fid[pid][r] = dict(lag_median_ms=float(np.median(lag)), lag_iqr_ms=float(q75 - q25),
                               beats_missed_pct=float((cnt == 0).mean() * 100),
                               beats_multi_pct=float((cnt >= 2).mean() * 100))

    df_all = pd.DataFrame(rows)
    df_all.to_csv(OUT / "wildppg_windows.csv", index=False)
    n_all = len(df_all)
    df = df_all[df_all["ref_rmssd"].notna() & (df_all["ref_reject_frac"] <= MAX_REF_REJECT)].reset_index(drop=True)
    total = len(df)

    def kept(run, comp, tau):
        ok = df[f"rmssd_{run}"].notna()
        return ok if (comp is None or tau <= 0) else ok & (df[f"{comp}_{run}"] >= tau)

    def m_of(mask, col):
        d = df[mask]
        e = (d[col] - d["ref_rmssd"]).to_numpy()
        return dict(coverage=float(mask.sum() / total), n_windows=int(mask.sum()),
                    **metrics(e, d[col].to_numpy(), d["ref_rmssd"].to_numpy()))

    sw = []
    for run in TICK_RUNS:
        for comp in ("sqi_full", "sqi_amp", "sqi_per"):
            for tau in TAUS:
                mk = kept(run, comp, tau)
                sw.append(dict(run=run, variant=comp, tau=float(tau), **m_of(mk, f"rmssd_{run}")))
    sw = pd.DataFrame(sw)
    sw.to_csv(OUT / "wildppg_sweep.csv", index=False)

    def pick(run, comp, tau):
        r = sw[(sw.run == run) & (sw.variant == comp) & np.isclose(sw.tau, tau)].iloc[0].to_dict()
        return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in r.items()}

    # block bootstrap (10-min blocks within participant) for median |error|
    rng = np.random.default_rng(SEED)
    blocks = df["block"].unique()
    by_blk = {b: np.flatnonzero(df["block"].to_numpy() == b) for b in blocks}
    masks = {"none": ("rmssd_app", kept("app", None, 0)),
             "sqi_full>=0.4": ("rmssd_app", kept("app", "sqi_full", APP_TAU)),
             "in_loop_0.4": ("rmssd_inloop_0.4", df["rmssd_inloop_0.4"].notna()),
             "systolic_none (not the app)": ("rmssd_systolic", kept("systolic", None, 0)),
             "v2_none (not the app)": ("rmssd_v2", kept("v2", None, 0))}
    for tau in HIGH_TAUS:
        masks[f"sqi_full>={tau} (post hoc)"] = ("rmssd_app", kept("app", "sqi_full", tau))
    ae = {k: np.abs(df[c].to_numpy() - df["ref_rmssd"].to_numpy()) for k, (c, _) in masks.items()}
    km = {k: m.to_numpy() for k, (_, m) in masks.items()}
    samp = {k: [] for k in masks}
    for _ in range(N_BOOT):
        idx = np.concatenate([by_blk[b] for b in rng.choice(blocks, len(blocks), replace=True)])
        for k in masks:
            sel = idx[km[k][idx]]
            samp[k].append(np.median(ae[k][sel]) if len(sel) else np.nan)
    boot = {}
    for k, v in samp.items():
        v = np.asarray(v)
        boot[k] = dict(ci95=[float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))])
        if k != "none":
            dv = np.asarray(samp["none"]) - v
            boot[k]["reduction_vs_none_ci95"] = [float(np.nanpercentile(dv, 2.5)), float(np.nanpercentile(dv, 97.5))]

    # motion gate at the same coverage as post-hoc SQI thresholds
    comp_ok = df[df["rmssd_app"].notna()].sort_values("acc_sd")
    high = {}
    for tau in HIGH_TAUS:
        mk = kept("app", "sqi_full", tau)
        k = int(mk.sum())
        mm = pd.Series(df.index.isin(comp_ok.index[:k]))
        high[str(tau)] = dict(sqi=m_of(mk, "rmssd_app"), motion_same_coverage=m_of(mm, "rmssd_app"),
                              ref_rmssd_median_kept=float(df.loc[mk, "ref_rmssd"].median()),
                              ref_rmssd_median_dropped=float(df.loc[~mk & df["rmssd_app"].notna(), "ref_rmssd"].median()))

    per_part = {}
    for pid, g in df.groupby("subject"):
        per_part[pid] = {}
        for label, col in (("app_none", "rmssd_app"), ("systolic_none (not the app)", "rmssd_systolic"),
                           ("green_none", "rmssd_green"), ("app_100hz_none", "rmssd_app_100hz")):
            mk = g[col].notna()
            e = (g.loc[mk, col] - g.loc[mk, "ref_rmssd"]).to_numpy()
            per_part[pid][label] = dict(coverage=float(mk.mean()), **metrics(e, g.loc[mk, col].to_numpy(), g.loc[mk, "ref_rmssd"].to_numpy()))
        per_part[pid]["sqi_full_app_median"] = float(g["sqi_full_app"].median())
        per_part[pid]["modulation_median_pct"] = float(g["mod_median_app"].median() * 100)
        per_part[pid]["frac_ticks_with_artifact_penalty"] = float(g["penalty_lt1_frac_app"].mean())

    summary = dict(
        dataset="WildPPG (ETH Zurich, NeurIPS 2024 D&B), CC BY-NC-SA 4.0; forehead MAX86141 PPG, sternum Lead-I ECG, 128 Hz",
        participants=pids, windows_total=n_all, windows_with_reliable_reference=total,
        params=dict(fs=128.0, win_s=WIN_S, start_s=START_S, n_min_ppg=N_MIN_PPG,
                    max_ref_reject_frac=MAX_REF_REJECT, bootstrap="10-min blocks within participant",
                    block_s=BLOCK_S, seed=SEED, n_boot=N_BOOT),
        ref_rmssd_ms=dict(median=float(df["ref_rmssd"].median()),
                          iqr=[float(df["ref_rmssd"].quantile(0.25)), float(df["ref_rmssd"].quantile(0.75))]),
        no_filter=pick("app", "sqi_full", 0.0),
        post_hoc_app_threshold={c: pick("app", c, APP_TAU) for c in ("sqi_full", "sqi_amp", "sqi_per")},
        in_loop_0_4=m_of(df["rmssd_inloop_0.4"].notna(), "rmssd_inloop_0.4"),
        dropped_by_sqi_0_4=m_of(kept("app", None, 0) & ~kept("app", "sqi_full", APP_TAU), "rmssd_app"),
        systolic_no_filter=pick("systolic", "sqi_full", 0.0),
        green_no_filter=pick("green", "sqi_full", 0.0),
        v2_no_filter=pick("v2", "sqi_full", 0.0),
        v2_in_loop_0_4=m_of(df["rmssd_v2_inloop_0.4"].notna(), "rmssd_v2_inloop_0.4"),
        app_100hz_no_filter=m_of(df["rmssd_app_100hz"].notna(), "rmssd_app_100hz"),
        high_threshold_post_hoc=high,
        bootstrap_median_abs_err=boot,
        per_participant=per_part,
        fiducial=fid,
    )
    (OUT / "wildppg_runtime.json").write_text(json.dumps({f"{k[0]}/{k[1]}": round(v[2], 1) for k, v in res.items()}, indent=2))
    (OUT / "wildppg_summary.json").write_text(json.dumps(summary, indent=2))
    (OUT / "wildppg_polarity.json").write_text(json.dumps(polarity, indent=2))
    print(f"done in {time.time() - t_start:.0f} s; windows {n_all}, with reliable reference {total}")


if __name__ == "__main__":
    main(tuple(sys.argv[1:]) or ("an0", "e61"))
