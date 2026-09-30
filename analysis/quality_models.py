"""Which signal best tells good from bad windows? (v2 pipeline)

Each method gives every window a score; windows are kept from the best score down.
Evaluation is leave-one-subject-out (LOSO): scores for a subject come from a model
fitted on the other subjects, and for single features the direction (higher = better
or worse) is also chosen on the other subjects.

Methods:
  single features   app SQI, accelerometer SD, template correlation, rejection count proxy, ...
  logistic          L2 logistic regression predicting "good" (|RMSSD error| <= 5 ms)
  gbm               gradient-boosted trees predicting log(1 + |error|)
  gbm_no_rmssd      same without the RMSSD estimate itself as a feature (selection-bias check)
  oracle            ranked by the true error (needs the ECG; ceiling)

Metrics (coverage = share of ALL windows with an ECG reference that is kept):
  median |error| at 25/50/75% coverage; AURC = mean of the median-|error| curve over
  coverages 10%..max; gap_closed = (AURC_no_gate - AURC) / (AURC_no_gate - AURC_oracle);
  AUROC for "good". 95% CIs: bootstrap over subjects of the out-of-fold scores.
Cross-site: fit on one dataset, score the other.

Output: results/quality_models.json, results/fig_quality_models.{png,pdf},
        results/oof_scores_{finger,forehead}.csv
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402
from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from features import FEATURES  # noqa: E402
from run_analysis import SEED  # noqa: E402

RES = Path(__file__).resolve().parent / "results"
GOOD_MS = 5.0
GRID = np.round(np.arange(0.10, 1.0001, 0.05), 2)
N_BOOT = 1000
SINGLE = ["sqi_full", "sqi_per", "acc_sd", "tmpl_corr_mean", "reject_frac", "rr_diff_max_rel", "skewness", "spec_purity"]
NO_RMSSD = [f for f in FEATURES if f != "ppg_rmssd"]


def load(name):
    d = pd.read_csv(RES / f"features_{name}.csv")
    d = d[d["ref_ok"]].reset_index(drop=True)
    d["ae"] = (d["rmssd_v2"] - d["ref_rmssd"]).abs()
    d["labelled"] = d["rmssd_v2"].notna()
    return d


def gbm():
    return HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200,
                                         min_samples_leaf=20, random_state=SEED)


def logistic():
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                         LogisticRegression(C=1.0, max_iter=2000))


def fit_score(train, test, method):
    """Higher score = keep first. Only labelled rows are used for fitting."""
    tr = train[train["labelled"]]
    if method in SINGLE:
        rho = spearmanr(tr[method], tr["ae"], nan_policy="omit")[0]
        sign = -1.0 if not np.isfinite(rho) or rho > 0 else 1.0
        sc = sign * test[method].to_numpy(dtype=float)
        worst = np.nanmin(sc) - 1.0 if np.isfinite(sc).any() else -1.0
        return np.where(np.isfinite(sc), sc, worst)      # missing feature = treated as worst
    if method == "logistic":
        m = logistic().fit(tr[FEATURES], (tr["ae"] <= GOOD_MS).astype(int))
        return m.predict_proba(test[FEATURES])[:, 1]
    feats = NO_RMSSD if method == "gbm_no_rmssd" else FEATURES
    m = gbm().fit(tr[feats], np.log1p(tr["ae"]))
    return -m.predict(test[feats])


METHODS = SINGLE + ["logistic", "gbm", "gbm_no_rmssd"]


def oof_scores(d):
    out = pd.DataFrame(index=d.index)
    for m in METHODS:
        s = np.full(len(d), np.nan)
        for subj in d["subject"].unique():
            te = (d["subject"] == subj).to_numpy()
            s[te] = fit_score(d[~te], d[te], m)
        out[m] = s
    out["oracle"] = -d["ae"].to_numpy()
    return out


def curve(ae, labelled, score, total):
    """median |error| of the top-k labelled windows for each coverage of `total` windows."""
    a, s = ae[labelled], score[labelled]
    order = np.argsort(-s, kind="stable")
    res = {}
    for c in GRID:
        k = int(round(c * total))
        if 5 <= k <= len(a):
            res[float(c)] = float(np.median(a[order[:k]]))
    return res


def summarize_curve(cv, base):
    vals = list(cv.values())
    return dict(aurc=float(np.mean(vals)) if vals else np.nan, at25=cv.get(0.25), at50=cv.get(0.5), at75=cv.get(0.75),
                no_gate=base)


def evaluate(d, scores, rng):
    ae, lab, total = d["ae"].to_numpy(), d["labelled"].to_numpy(), len(d)
    base = float(np.median(ae[lab]))
    res = {}
    cvs = {}
    for m in list(scores.columns):
        cv = curve(ae, lab, scores[m].to_numpy(), total)
        cvs[m] = cv
        r = summarize_curve(cv, base)
        good = (ae[lab] <= GOOD_MS).astype(int)
        if m != "oracle" and 0 < good.sum() < len(good):
            r["auroc_good"] = float(roc_auc_score(good, scores[m].to_numpy()[lab]))
        res[m] = r
    orc = res["oracle"]["aurc"]
    for m in res:
        res[m]["gap_closed"] = float((base - res[m]["aurc"]) / (base - orc)) if base != orc else np.nan
    # bootstrap over subjects: AURC and difference vs the app SQI
    subjects = d["subject"].unique()
    by = {s: np.flatnonzero(d["subject"].to_numpy() == s) for s in subjects}
    boot = {m: [] for m in scores.columns}
    for _ in range(N_BOOT):
        idx = np.concatenate([by[s] for s in rng.choice(subjects, len(subjects), replace=True)])
        for m in scores.columns:
            cv = curve(ae[idx], lab[idx], scores[m].to_numpy()[idx], len(idx))
            boot[m].append(np.mean(list(cv.values())) if cv else np.nan)
    for m in scores.columns:
        b = np.asarray(boot[m])
        res[m]["aurc_ci95"] = [float(np.nanpercentile(b, 2.5)), float(np.nanpercentile(b, 97.5))]
        dv = np.asarray(boot["sqi_full"]) - b
        res[m]["aurc_improvement_vs_sqi_ci95"] = [float(np.nanpercentile(dv, 2.5)), float(np.nanpercentile(dv, 97.5))]
    # selection-bias check at 50% coverage
    for m in scores.columns:
        s = scores[m].to_numpy()
        idx = np.flatnonzero(lab)
        k = int(round(0.5 * total))
        if k <= len(idx):
            keep = idx[np.argsort(-s[idx], kind="stable")[:k]]
            drop = np.setdiff1d(idx, keep)
            res[m]["ref_rmssd_median_kept50"] = float(np.median(d["ref_rmssd"].to_numpy()[keep]))
            res[m]["ref_rmssd_median_dropped50"] = float(np.median(d["ref_rmssd"].to_numpy()[drop])) if len(drop) else None
    return res, cvs, base


def cross_site(src, dst):
    tr = src[src["labelled"]]
    out = pd.DataFrame(index=dst.index)
    for m in ["sqi_full", "acc_sd", "tmpl_corr_mean", "reject_frac"]:
        out[m] = fit_score(src, dst, m)
    out["logistic"] = logistic().fit(tr[FEATURES], (tr["ae"] <= GOOD_MS).astype(int)).predict_proba(dst[FEATURES])[:, 1]
    out["gbm"] = -gbm().fit(tr[FEATURES], np.log1p(tr["ae"])).predict(dst[FEATURES])
    out["oracle"] = -dst["ae"].to_numpy()
    ae, lab = dst["ae"].to_numpy(), dst["labelled"].to_numpy()
    base = float(np.median(ae[lab]))
    return {m: summarize_curve(curve(ae, lab, out[m].to_numpy(), len(dst)), base) for m in out.columns}


def main():
    rng = np.random.default_rng(SEED)
    result, curves = {}, {}
    data = {}
    for name in ("finger", "forehead"):
        p = RES / f"features_{name}.csv"
        if not p.exists():
            continue
        d = load(name)
        data[name] = d
        sc = oof_scores(d)
        sc.assign(subject=d["subject"], t0=d["t0"]).to_csv(RES / f"oof_scores_{name}.csv", index=False)
        res, cvs, base = evaluate(d, sc, rng)
        result[name] = dict(windows_with_reference=int(len(d)), labelled=int(d["labelled"].sum()),
                            subjects=int(d["subject"].nunique()), good_pct=float((d.loc[d["labelled"], "ae"] <= GOOD_MS).mean() * 100),
                            no_gate_median_abs_err=base, methods=res)
        curves[name] = cvs
    if len(data) == 2:
        result["cross_site"] = {"finger->forehead": cross_site(data["finger"], data["forehead"]),
                                "forehead->finger": cross_site(data["forehead"], data["finger"])}
    (RES / "quality_models.json").write_text(json.dumps(result, indent=2))

    # figure: risk-coverage per dataset
    SURFACE, INK, INK2, GRIDC = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    show = [("oracle", "Oracle (needs ECG)", INK, "-"), ("sqi_full", "App SQI", "#2a78d6", "-"),
            ("acc_sd", "Accelerometer", "#eb6834", "-"), ("tmpl_corr_mean", "Beat-template correlation", "#1baf7a", "-"),
            ("gbm", "Gradient boosting, all features", "#4a3aa7", "--")]
    fig, axes = plt.subplots(1, len(curves), figsize=(4.6 * len(curves), 3.8), facecolor=SURFACE, squeeze=False)
    for ax, (name, cvs) in zip(axes[0], curves.items()):
        ax.set_facecolor(SURFACE)
        ax.grid(True, color=GRIDC, linewidth=0.6)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for m, lab, col, ls in show:
            cv = cvs[m]
            ax.plot(np.array(list(cv)) * 100, list(cv.values()), color=col, linestyle=ls, linewidth=2,
                    label=lab, marker="o", markersize=3, markeredgecolor=SURFACE, markeredgewidth=0.6)
        ax.axhline(result[name]["no_gate_median_abs_err"], color=INK2, linestyle=":", linewidth=1)
        ax.text(2, result[name]["no_gate_median_abs_err"], " no gate", color=INK2, fontsize=7.5, va="bottom")
        ttl = {"finger": "A  Finger, lab (22 subjects)", "forehead": f"B  Forehead, daily life ({result[name]['subjects']} participants)"}[name]
        ax.set_title(ttl, loc="left", fontsize=9.5, color=INK)
        ax.set_xlabel("Windows kept (% of windows with ECG reference)")
        ax.set_ylabel("Median |RMSSD error| (ms)")
        ax.set_xlim(0, 100)
        ax.set_ylim(0, None)
    h, lab = axes[0][0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=3, frameon=False, fontsize=8, bbox_to_anchor=(0.5, 0.03))
    fig.text(0.01, 0.005, "v2 pipeline. Every score comes from a model or direction fitted on the other subjects "
             "(leave-one-subject-out).", fontsize=7, color=INK2)
    fig.tight_layout(rect=(0, 0.14, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(RES / f"fig_quality_models.{ext}", dpi=200, facecolor=SURFACE)


if __name__ == "__main__":
    main()
