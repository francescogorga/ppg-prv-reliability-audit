"""Test 1: how much could ANY window-level quality gate reduce RMSSD error?

For each dataset and pipeline variant, windows are ranked and the best k are kept,
for coverages from 5% to 100% of the windows with a valid ECG reference:
  oracle      ranked by the true |error| (uses the ECG; unreachable, it is the ceiling)
  sqi_full    ranked by the app's window SQI (highest first)
  sqi_per     ranked by the periodicity term alone
  motion      ranked by accelerometer SD (lowest first)
Ties are broken by a seeded random order. A random gate keeps the median error of
the whole set, so "no gate" is also the random-gate reference.

Also reports how many windows are actually good (|error| <= 5 ms, <= 20% of the
true RMSSD): a gate can only keep good windows that exist.

Reads results/windows.csv and results/wildppg_windows.csv.
Writes results/oracle_check.json and results/fig_oracle.{png,pdf}.
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from run_analysis import SEED  # noqa: E402
from run_wildppg import MAX_REF_REJECT  # noqa: E402

RES = Path(__file__).resolve().parent / "results"
COVERAGES = np.round(np.arange(0.05, 1.0001, 0.05), 2)
MIN_KEEP = 20

DATASETS = {
    "finger_lab": dict(csv="windows.csv", runs={
        "app": ("rmssd_off", "sqi_full_off", "sqi_per_off"),
        "systolic (not in app)": ("rmssd_inverted_off", "sqi_full_inverted_off", "sqi_per_inverted_off")}),
    "forehead_daily_life": dict(csv="wildppg_windows.csv", runs={
        "app": ("rmssd_app", "sqi_full_app", "sqi_per_app"),
        "systolic (not in app)": ("rmssd_systolic", "sqi_full_systolic", "sqi_per_systolic"),
        "green, app polarity": ("rmssd_green", "sqi_full_green", "sqi_per_green")}),
}


def load(name, spec):
    df = pd.read_csv(RES / spec["csv"])
    df = df[df["ref_rmssd"].notna()]
    if "ref_reject_frac" in df:
        df = df[df["ref_reject_frac"] <= MAX_REF_REJECT]
    return df.reset_index(drop=True)


def curve(ae, score, total, rng, higher_is_better=True):
    """median |error| of the best-k windows by `score`, for each coverage."""
    tie = rng.permutation(len(ae))
    key = -score if higher_is_better else score
    order = np.lexsort((tie, key))
    out = {}
    for c in COVERAGES:
        k = int(round(c * total))
        if k < MIN_KEEP or k > len(ae):
            continue
        out[float(c)] = float(np.median(ae[order[:k]]))
    return out


def main():
    rng = np.random.default_rng(SEED)
    summary, curves = {}, {}
    for name, spec in DATASETS.items():
        df = load(name, spec)
        total = len(df)
        summary[name] = {"windows_with_reference": total}
        for run, (col, sqi, per) in spec["runs"].items():
            d = df[df[col].notna()]
            ae = np.abs(d[col].to_numpy() - d["ref_rmssd"].to_numpy())
            rel = ae / d["ref_rmssd"].to_numpy()
            c = {
                "oracle": curve(ae, ae, total, rng, higher_is_better=False),
                "sqi_full": curve(ae, d[sqi].fillna(-1).to_numpy(), total, rng),
                "sqi_per": curve(ae, d[per].fillna(-1).to_numpy(), total, rng),
                "motion": curve(ae, d["acc_sd"].to_numpy(), total, rng, higher_is_better=False),
            }
            curves[(name, run)] = c
            cov_max = len(d) / total
            summary[name][run] = dict(
                computable_coverage=float(cov_max),
                no_gate_median_abs_err=float(np.median(ae)),
                good_windows_pct_of_computable={
                    "abs_err<=5ms": float(np.mean(ae <= 5) * 100),
                    "abs_err<=10ms": float(np.mean(ae <= 10) * 100),
                    "rel_err<=20%": float(np.mean(rel <= 0.20) * 100),
                },
                good_windows_pct_of_all_with_reference={
                    "abs_err<=5ms": float(np.sum(ae <= 5) / total * 100),
                    "rel_err<=20%": float(np.sum(rel <= 0.20) / total * 100),
                },
                at_coverage={f"{int(cv * 100)}%": {g: c[g].get(cv) for g in c}
                             for cv in (0.1, 0.2, 0.3, 0.5, float(np.floor(0.8 * cov_max * 20) / 20)) if cv <= cov_max},
            )
    (RES / "oracle_check.json").write_text(json.dumps(summary, indent=2))

    # figure: one panel per dataset, app pipeline and systolic variant
    SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    style = {"oracle": ("Oracle (ranked by true error, needs ECG)", INK, "-", 2.2),
             "sqi_full": ("Full SQI (app)", "#2a78d6", "-", 2),
             "sqi_per": ("Periodicity term only", "#1baf7a", "-", 2),
             "motion": ("Accelerometer (least motion first)", "#eb6834", "-", 2)}
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK,
                         "xtick.color": INK2, "ytick.color": INK2})
    fig, axes = plt.subplots(2, 2, figsize=(9, 6.6), facecolor=SURFACE)
    panels = [("finger_lab", "app"), ("finger_lab", "systolic (not in app)"),
              ("forehead_daily_life", "app"), ("forehead_daily_life", "systolic (not in app)")]
    titles = ["A  Finger, lab — app pipeline", "B  Finger, lab — systolic-peak timing (not in app)",
              "C  Forehead, daily life — app pipeline", "D  Forehead, daily life — systolic-peak timing (not in app)"]
    for ax, key, title in zip(axes.flat, panels, titles):
        ax.set_facecolor(SURFACE)
        ax.grid(True, color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for g, (lab, col, ls, lw) in style.items():
            cv = curves[key][g]
            ax.plot(np.array(list(cv)) * 100, list(cv.values()), color=col, linestyle=ls, linewidth=lw,
                    label=lab, marker="o", markersize=3, markeredgecolor=SURFACE, markeredgewidth=0.6)
        ax.set_title(title, loc="left", fontsize=9, color=INK)
        if key[0] == "finger_lab":
            ax.text(0.98, 0.04, "Full SQI = periodicity ranking here\n(amplitude term is always 1)", transform=ax.transAxes,
                    ha="right", va="bottom", fontsize=7.3, color=INK2)
        ax.set_xlabel("Windows kept (% of windows with ECG reference)")
        ax.set_ylabel("Median |RMSSD error| (ms)")
        ax.set_xlim(0, 100)
        ax.set_ylim(0, None)
    h, lab = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=2, frameon=False, fontsize=8, bbox_to_anchor=(0.5, 0.0))
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(RES / f"fig_oracle.{ext}", dpi=200, facecolor=SURFACE)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
