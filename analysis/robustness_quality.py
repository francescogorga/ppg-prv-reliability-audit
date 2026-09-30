"""Are the quality-model results real, or artefacts of who/what is in the data?

Uses the leave-one-subject-out scores saved by quality_models.py.
1. Finger: does a method still rank windows WITHIN one activity (sit, walk, run)?
   If it only separated sitting from moving, within-activity ranking would be poor.
2. Forehead: does it rank windows WITHIN one participant's day? If it only recognised
   participants with good signals, within-participant ranking would be poor.
3. Label threshold: AUROC with "good" = |error| <= 5, 10, 20 ms and PR-AUC for 5 ms
   (good windows are rare at the forehead, so AUROC alone can flatter).
4. Circularity. The label is |RMSSD_ppg - RMSSD_ecg|; when errors are large, gating on a
   low RMSSD_ppg lowers the kept error by construction. Two extra gates:
     ppg_rmssd_low     keep the windows with the lowest RMSSD estimate (no model)
     gbm_signal_only   gradient boosting WITHOUT the RMSSD estimate and the RR-variability
                       features (rr_cv, rr_diff_*, SQI periodicity and full SQI)
   and, on the windows each gate keeps, whether the estimate still TRACKS ECG-derived RMSSD
   (Spearman and Pearson between RMSSD_ppg and RMSSD_ecg) - lowering the error is not
   enough if the kept values do not follow the ECG reference.
Metrics per subset: Spearman between score and |error| (sign flipped: higher = better)
and gap closed (same definition as quality_models.py, computed inside the subset).
Output: results/robustness_quality.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import average_precision_score, roc_auc_score

from features import FEATURES
from quality_models import curve, gbm, load
from run_analysis import SEED

RES = Path(__file__).resolve().parent / "results"
METHODS = ["sqi_full", "acc_sd", "tmpl_corr_mean", "reject_frac", "logistic", "gbm", "gbm_no_rmssd",
           "ppg_rmssd_low", "gbm_signal_only", "oracle"]
RR_DERIVED = {"ppg_rmssd", "rr_cv", "rr_diff_mad_rel", "rr_diff_max_rel", "sqi_per", "sqi_full"}
SIGNAL_ONLY = [f for f in FEATURES if f not in RR_DERIVED]
KEEP = {"finger": 0.50, "forehead": 0.25}
N_BOOT = 1000
TRACK_METHODS = ["sqi_full", "acc_sd", "tmpl_corr_mean", "reject_frac", "gbm", "gbm_signal_only", "ppg_rmssd_low", "oracle"]


def tracking_boot(d, sc, cov, rng):
    """Subject bootstrap of the Spearman(RMSSD_ppg, RMSSD_ecg) on the windows each gate keeps."""
    lab = d["labelled"].to_numpy()
    subj = d["subject"].to_numpy()
    subjects = np.unique(subj)
    by = {s: np.flatnonzero(subj == s) for s in subjects}
    ppg_all, ref_all = d["rmssd_v2"].to_numpy(), d["ref_rmssd"].to_numpy()
    res = {m: [] for m in TRACK_METHODS + ["no_gate"]}
    for _ in range(N_BOOT):
        idx = np.concatenate([by[s] for s in rng.choice(subjects, len(subjects), replace=True)])
        li = idx[lab[idx]]
        k = int(round(cov * len(idx)))
        res["no_gate"].append(spearmanr(ppg_all[li], ref_all[li])[0])
        for m in TRACK_METHODS:
            s = sc[m].to_numpy()[li]
            keep = li[np.argsort(-s, kind="stable")[:k]]
            res[m].append(spearmanr(ppg_all[keep], ref_all[keep])[0])
    out = {m: [float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))] for m, v in res.items()}
    d_tp = np.asarray(res["tmpl_corr_mean"]) - np.asarray(res["ppg_rmssd_low"])
    d_ts = np.asarray(res["tmpl_corr_mean"]) - np.asarray(res["sqi_full"])
    out["diff_tmpl_minus_ppg_rmssd_low"] = [float(np.nanpercentile(d_tp, 2.5)), float(np.nanpercentile(d_tp, 97.5))]
    out["diff_tmpl_minus_sqi"] = [float(np.nanpercentile(d_ts, 2.5)), float(np.nanpercentile(d_ts, 97.5))]
    return out


def extra_scores(d, sc):
    sc = sc.copy()
    r = d["ppg_rmssd"].to_numpy(dtype=float)
    sc["ppg_rmssd_low"] = np.where(np.isfinite(r), -r, np.nanmin(-r) - 1)
    s = np.full(len(d), np.nan)
    for subj in d["subject"].unique():
        te = (d["subject"] == subj).to_numpy()
        tr = d[~te & d["labelled"].to_numpy()]
        s[te] = -gbm().fit(tr[SIGNAL_ONLY], np.log1p(tr["ae"])).predict(d.loc[te, SIGNAL_ONLY])
    sc["gbm_signal_only"] = s
    return sc


def pooled(d, sc, cov):
    ae, lab, total = d["ae"].to_numpy(), d["labelled"].to_numpy(), len(d)
    base = float(np.median(ae[lab]))
    orc = np.mean(list(curve(ae, lab, -ae, total).values()))
    idx = np.flatnonzero(lab)
    k = int(round(cov * total))
    out = {}
    for m in METHODS:
        s = sc[m].to_numpy()
        aurc = np.mean(list(curve(ae, lab, s, total).values()))
        keep = idx[np.argsort(-s[idx], kind="stable")[:k]]
        ppg, ref = d["rmssd_v2"].to_numpy()[keep], d["ref_rmssd"].to_numpy()[keep]
        out[m] = dict(gap_closed=float((base - aurc) / (base - orc)),
                      kept=dict(coverage=cov, median_abs_err=float(np.median(ae[keep])),
                                spearman_ppg_vs_ecg=float(spearmanr(ppg, ref)[0]),
                                pearson_ppg_vs_ecg=float(np.corrcoef(ppg, ref)[0, 1]),
                                median_ppg=float(np.median(ppg)), median_ecg=float(np.median(ref))))
    return out


def subset_metrics(d, sc, mask):
    sub, s = d[mask], sc[mask]
    ae, lab = sub["ae"].to_numpy(), sub["labelled"].to_numpy()
    if lab.sum() < 20:
        return None
    base = float(np.median(ae[lab]))
    orc = np.mean(list(curve(ae, lab, -ae, len(sub)).values()))
    out = {}
    for m in METHODS:
        cv = curve(ae, lab, s[m].to_numpy(), len(sub))
        aurc = np.mean(list(cv.values()))
        rho = spearmanr(s[m].to_numpy()[lab], ae[lab])[0]
        out[m] = dict(rho=float(-rho), gap_closed=float((base - aurc) / (base - orc)) if base > orc else None)
    return out


def summarize(per):
    res = {}
    for m in METHODS:
        rhos = [v[m]["rho"] for v in per.values() if v and np.isfinite(v[m]["rho"])]
        gaps = [v[m]["gap_closed"] for v in per.values() if v and v[m]["gap_closed"] is not None]
        res[m] = dict(rho_median=float(np.median(rhos)), rho_min=float(np.min(rhos)),
                      gap_closed_median=float(np.median(gaps)), gap_closed_min=float(np.min(gaps)), n_subsets=len(rhos))
    return res


def main():
    out = {}
    rng = np.random.default_rng(SEED)
    for name, group in (("finger", "activity"), ("forehead", "subject")):
        d = load(name)
        sc = pd.read_csv(RES / f"oof_scores_{name}.csv")
        assert (sc["subject"].astype(str).to_numpy() == d["subject"].astype(str).to_numpy()).all()
        assert np.allclose(sc["t0"].to_numpy(), d["t0"].to_numpy())
        sc = extra_scores(d, sc)
        per = {str(g): subset_metrics(d, sc, (d[group] == g).to_numpy()) for g in d[group].unique()}
        out[name] = {f"within_{group}": dict(summary=summarize(per), per_group=per)}
        lab = d["labelled"].to_numpy()
        thr = {}
        for t in (5, 10, 20):
            y = (d["ae"].to_numpy()[lab] <= t).astype(int)
            thr[f"good<={t}ms"] = dict(prevalence=float(y.mean()), auroc={
                m: float(roc_auc_score(y, sc[m].to_numpy()[lab])) for m in METHODS if m != "oracle"} if 0 < y.sum() < len(y) else None)
        y5 = (d["ae"].to_numpy()[lab] <= 5).astype(int)
        thr["pr_auc_good<=5ms"] = {m: float(average_precision_score(y5, sc[m].to_numpy()[lab])) for m in METHODS if m != "oracle"}
        out[name]["label_thresholds"] = thr
        out[name]["pooled_with_tracking"] = pooled(d, sc, KEEP[name])
        L = d[d["labelled"]]
        out[name]["no_gate_tracking"] = dict(spearman=float(spearmanr(L["rmssd_v2"], L["ref_rmssd"])[0]),
                                             pearson=float(np.corrcoef(L["rmssd_v2"], L["ref_rmssd"])[0, 1]),
                                             median_abs_err=float(L["ae"].median()))
        out[name]["tracking_ci95"] = tracking_boot(d, sc, KEEP[name], rng)
    (RES / "robustness_quality.json").write_text(json.dumps(out, indent=2))
    for name in out:
        g = list(out[name])[0]
        print("==", name, g)
        for m, v in out[name][g]["summary"].items():
            print(f"  {m:15s} rho median {v['rho_median']:+.2f} (min {v['rho_min']:+.2f}) | gap median {v['gap_closed_median']*100:4.0f}% (min {v['gap_closed_min']*100:4.0f}%) n={v['n_subsets']}")
        lt = out[name]["label_thresholds"]
        for k in ("good<=5ms", "good<=10ms", "good<=20ms"):
            print(f"  {k} prev {lt[k]['prevalence']*100:.1f}%:", {m: round(a, 2) for m, a in (lt[k]['auroc'] or {}).items()})
        print("  PR-AUC <=5ms:", {m: round(a, 2) for m, a in lt["pr_auc_good<=5ms"].items()})
        print("  no gate tracking", out[name]["no_gate_tracking"])
        print("  tracking CI", {k: [round(a, 2) for a in v] for k, v in out[name]["tracking_ci95"].items()})
        for m, v in out[name]["pooled_with_tracking"].items():
            k = v["kept"]
            print(f"  pooled {m:15s} gap {v['gap_closed']*100:4.0f}% | keep {k['coverage']*100:.0f}%: err {k['median_abs_err']:6.1f} "
                  f"| rho(ppg,ecg) {k['spearman_ppg_vs_ecg']:+.2f} r {k['pearson_ppg_vs_ecg']:+.2f} | median ppg {k['median_ppg']:.1f} ecg {k['median_ecg']:.1f}")


if __name__ == "__main__":
    main()
