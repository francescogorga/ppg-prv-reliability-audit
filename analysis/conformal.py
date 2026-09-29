"""Uncertainty: calibrated intervals for the v2 RMSSD, with split conformal prediction.

For each window the interval is  RMSSD_ppg +- q * sigma(x):
  adaptive  sigma(x) = predicted |error| + 1 ms (gradient boosting on the features,
            fitted on log(1 + |error|)); q from the calibration set so that 90% of
            calibration windows satisfy |error| <= q * sigma(x)
  constant  sigma(x) = 1 (same width for every window)
Split conformal guarantees 90% coverage on average only if test windows are
exchangeable with calibration windows. We check where that holds:
  within dataset: the test subject is never used; the other subjects are split at
      random into training (2/3) and calibration (1/3), 20 repeats per test subject.
      Reported: pooled coverage, per-subject coverage (conditional), median width.
  shift: calibrate on one dataset, test on the other (finger <-> forehead).
  selective: keep only windows whose adaptive interval is narrower than W ms.
Output: results/conformal.json, results/fig_conformal.{png,pdf}
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from features import FEATURES  # noqa: E402
from quality_models import gbm, load  # noqa: E402
from run_analysis import SEED  # noqa: E402

RES = Path(__file__).resolve().parent / "results"
ALPHA = 0.10
DELTA = 1.0
REPEATS = 20
WIDTHS = (10.0, 20.0, 40.0)


def conformal_q(scores):
    n = len(scores)
    k = min(int(np.ceil((n + 1) * (1 - ALPHA))), n)
    return float(np.sort(scores)[k - 1])


def fit_predict(train, calib, test):
    m = gbm().fit(train[FEATURES], np.log1p(train["ae"]))
    sig_c = np.expm1(m.predict(calib[FEATURES])) + DELTA
    sig_t = np.expm1(m.predict(test[FEATURES])) + DELTA
    q_ad = conformal_q(calib["ae"].to_numpy() / sig_c)
    q_co = conformal_q(calib["ae"].to_numpy())
    ae = test["ae"].to_numpy()
    return dict(cov_ad=ae <= q_ad * sig_t, width_ad=2 * q_ad * sig_t,
                cov_co=ae <= q_co, width_co=np.full(len(ae), 2 * q_co))


def within(d, rng):
    d = d[d["labelled"]].reset_index(drop=True)
    subjects = d["subject"].unique()
    per_subj, pooled = {}, {k: [] for k in ("cov_ad", "width_ad", "cov_co", "width_co")}
    sel = {w: dict(kept=[], ae=[], cov=[]) for w in WIDTHS}
    for s in subjects:
        te = d[d["subject"] == s]
        others = np.array([x for x in subjects if x != s])
        acc = {k: [] for k in pooled}
        for _ in range(REPEATS):
            perm = rng.permutation(others)
            ntr = int(round(len(perm) * 2 / 3))
            tr, ca = d[d["subject"].isin(perm[:ntr])], d[d["subject"].isin(perm[ntr:])]
            r = fit_predict(tr, ca, te)
            for k in acc:
                acc[k].append(r[k])
            for w in WIDTHS:
                keep = r["width_ad"] <= w
                sel[w]["kept"].append(keep)
                sel[w]["ae"].append(te["ae"].to_numpy()[keep])
                sel[w]["cov"].append(r["cov_ad"][keep])
        per_subj[str(s)] = dict(n=int(len(te)), cov_adaptive=float(np.mean(acc["cov_ad"])),
                                cov_constant=float(np.mean(acc["cov_co"])),
                                width_adaptive_median=float(np.median(np.concatenate(acc["width_ad"]))),
                                width_constant=float(np.median(np.concatenate(acc["width_co"]))))
        for k in pooled:
            pooled[k].append(np.concatenate(acc[k]))
    P = {k: np.concatenate(v) for k, v in pooled.items()}
    cov_ad = [v["cov_adaptive"] for v in per_subj.values()]
    cov_co = [v["cov_constant"] for v in per_subj.values()]
    out = dict(
        target=1 - ALPHA, repeats=REPEATS,
        pooled=dict(coverage_adaptive=float(P["cov_ad"].mean()), coverage_constant=float(P["cov_co"].mean()),
                    width_adaptive_median=float(np.median(P["width_ad"])), width_constant_median=float(np.median(P["width_co"])),
                    width_adaptive_p10_p90=[float(np.percentile(P["width_ad"], 10)), float(np.percentile(P["width_ad"], 90))]),
        per_subject_coverage=dict(adaptive_min=float(np.min(cov_ad)), adaptive_p10=float(np.percentile(cov_ad, 10)),
                                  constant_min=float(np.min(cov_co)), constant_p10=float(np.percentile(cov_co, 10)),
                                  subjects_below_80pct_adaptive=int(np.sum(np.array(cov_ad) < 0.8)),
                                  subjects_below_80pct_constant=int(np.sum(np.array(cov_co) < 0.8))),
        selective={f"width<={int(w)}ms": dict(
            kept_pct_of_labelled=float(np.concatenate(sel[w]["kept"]).mean() * 100),
            median_abs_err=float(np.median(np.concatenate(sel[w]["ae"]))) if np.concatenate(sel[w]["ae"]).size else None,
            interval_coverage=float(np.concatenate(sel[w]["cov"]).mean()) if np.concatenate(sel[w]["cov"]).size else None)
            for w in WIDTHS},
        per_subject=per_subj,
    )
    return out, cov_ad, cov_co


def shift(src, dst, rng):
    src = src[src["labelled"]].reset_index(drop=True)
    dst = dst[dst["labelled"]].reset_index(drop=True)
    subjects = src["subject"].unique()
    res = []
    for _ in range(REPEATS):
        perm = rng.permutation(subjects)
        ntr = int(round(len(perm) * 2 / 3))
        r = fit_predict(src[src["subject"].isin(perm[:ntr])], src[src["subject"].isin(perm[ntr:])], dst)
        res.append(r)
    return dict(coverage_adaptive=float(np.mean([r["cov_ad"].mean() for r in res])),
                coverage_constant=float(np.mean([r["cov_co"].mean() for r in res])),
                width_adaptive_median=float(np.median(np.concatenate([r["width_ad"] for r in res]))),
                width_constant_median=float(np.median(np.concatenate([r["width_co"] for r in res]))))


def main():
    rng = np.random.default_rng(SEED)
    data = {n: load(n) for n in ("finger", "forehead") if (RES / f"features_{n}.csv").exists()}
    result, percov = {}, {}
    for n, d in data.items():
        result[n], ca, cc = within(d, rng)
        percov[n] = (ca, cc)
    if len(data) == 2:
        result["shift"] = {"calibrate finger -> test forehead": shift(data["finger"], data["forehead"], rng),
                           "calibrate forehead -> test finger": shift(data["forehead"], data["finger"], rng)}
    (RES / "conformal.json").write_text(json.dumps(result, indent=2))

    SURFACE, INK, INK2, GRIDC = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    fig, axes = plt.subplots(1, len(percov), figsize=(4.4 * len(percov), 3.4), facecolor=SURFACE, squeeze=False)
    for ax, (n, (ca, cc)) in zip(axes[0], percov.items()):
        ax.set_facecolor(SURFACE)
        ax.grid(True, axis="y", color=GRIDC, linewidth=0.6)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        order = np.argsort(ca)
        x = np.arange(len(ca))
        ax.scatter(x, np.array(cc)[order] * 100, color="#eb6834", s=16, label="Constant width", zorder=3)
        ax.scatter(x, np.array(ca)[order] * 100, color="#2a78d6", s=16, label="Adaptive width (model)", zorder=3)
        ax.axhline(90, color=INK2, linestyle=":", linewidth=1)
        ax.text(0, 91, "target 90%", color=INK2, fontsize=7.5)
        ax.set_ylim(0, 102)
        ax.set_xlabel("Test subject (sorted by adaptive coverage)")
        ax.set_ylabel("Interval coverage (%)")
        ax.set_title({"finger": "A  Finger, lab", "forehead": "B  Forehead, daily life"}[n] + " — per-subject coverage",
                     loc="left", fontsize=9, color=INK)
        ax.set_xticks([])
    h, lab = axes[0][0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=2, frameon=False, fontsize=8)
    fig.tight_layout(rect=(0, 0.1, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(RES / f"fig_conformal.{ext}", dpi=200, facecolor=SURFACE)


if __name__ == "__main__":
    main()
