"""Brief figure, two panels.
A  HRV (finger, lab): error of kept windows vs whether kept RMSSD follows the ECG, per gate.
B  Stress: Cohen's kappa between the stress level the app shows (calm / aroused / stressed)
   and the level it would show from ECG HR/HRV, against the share of minutes shown.
Reads results/robustness_quality.json and results/stress_eval.json.
Writes results/fig_brief.{png,pdf}.
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RES = Path(__file__).resolve().parent / "results"
SURFACE, INK, INK2, GRID, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#8f8e89"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"


def panel_a(ax, R):
    r = R["finger"]
    pts = [("no_gate", "no gate", MUTED, "x"), ("sqi_full", "app SQI", BLUE, "o"),
           ("acc_sd", "accelerometer", MUTED, "^"), ("ppg_rmssd_low", "keep lowest\nestimates", ORANGE, "v"),
           ("tmpl_corr_mean", "beat-template\ncorrelation", AQUA, "o"), ("oracle", "oracle (ECG)", INK, "*")]
    offs = {"no_gate": (-40, 8), "sqi_full": (8, -3), "acc_sd": (8, -10), "ppg_rmssd_low": (8, -4),
            "tmpl_corr_mean": (-64, -14), "oracle": (8, 2)}
    for m, lab, col, mk in pts:
        if m == "no_gate":
            x, y = r["no_gate_tracking"]["median_abs_err"], r["no_gate_tracking"]["spearman"]
        else:
            k = r["pooled_with_tracking"][m]["kept"]
            x, y = k["median_abs_err"], k["spearman_ppg_vs_ecg"]
        lo, hi = r["tracking_ci95"][m]
        ax.errorbar(x, y, yerr=[[y - lo], [hi - y]], fmt="none", ecolor=col, alpha=0.4, linewidth=1.2, capsize=2)
        ax.scatter(x, y, color=col, marker=mk, s=60, edgecolors=None if mk == "x" else SURFACE, linewidths=0.8, zorder=3)
        ax.annotate(lab, (x, y), xytext=offs[m], textcoords="offset points", fontsize=7.5, color=col if col != MUTED else INK2)
    ax.set_xlim(2, 19.5)
    ax.set_ylim(-0.25, 1.0)
    ax.set_xlabel("Median |RMSSD error| of kept windows (ms)")
    ax.set_ylabel("Kept RMSSD vs ECG RMSSD (Spearman)")
    ax.set_title("A  PPG RMSSD, finger: keep 50% of windows", loc="left", fontsize=9.5, color=INK)


def panel_b(ax, S):
    for name, ls, lab in (("finger", "-", "finger, lab"), ("forehead", "--", "forehead, daily life")):
        r = S[name]["rules"]
        for key, col, mk, glab in (("v2_consistency", AQUA, "o", "beat-consistency gate"),):
            rules = ["v2", f"{key}@50%", f"{key}@25%"]
            xs = [r[k]["coverage"] * 100 for k in rules]
            ys = [r[k]["kappa"] for k in rules]
            lo = [r[k]["kappa"] - r[k]["kappa_ci95"][0] for k in rules]
            hi = [r[k]["kappa_ci95"][1] - r[k]["kappa"] for k in rules]
            ax.errorbar(xs, ys, yerr=[lo, hi], color=col, linestyle=ls, marker=mk, markersize=5, linewidth=1.8,
                        capsize=2, elinewidth=0.9, alpha=0.95, label=f"fixed beat timing + {glab} ({lab})")
        v1 = r["v1_app"]
        ax.errorbar(v1["coverage"] * 100, v1["kappa"], yerr=[[v1["kappa"] - v1["kappa_ci95"][0]], [v1["kappa_ci95"][1] - v1["kappa"]]],
                    color=BLUE, marker="s", markersize=6, capsize=2, linestyle="none",
                    label="app as deployed" if name == "finger" else None)
        ax.annotate(lab, (r["v2"]["coverage"] * 100, r["v2"]["kappa"]), xytext=(-70, 8 if name == "finger" else -14),
                    textcoords="offset points", fontsize=7.5, color=INK2)
    ax.set_xlim(0, 108)
    ax.set_ylim(0, 1.0)
    ax.set_xlabel("Minutes on which a stress level is shown (%)")
    ax.set_ylabel("Agreement with ECG-based app level (Cohen's kappa)")
    ax.set_title("B  Stress index: agreement vs minutes shown", loc="left", fontsize=9.5, color=INK)
    ax.legend(loc="upper right", fontsize=7, frameon=False)


def main():
    R = json.load(open(RES / "robustness_quality.json"))
    S = json.load(open(RES / "stress_eval.json"))
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK,
                         "xtick.color": INK2, "ytick.color": INK2})
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4.2), facecolor=SURFACE)
    for ax in (a, b):
        ax.set_facecolor(SURFACE)
        ax.grid(True, color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    panel_a(a, R)
    panel_b(b, S)
    fig.text(0.01, 0.005, "Bars: 95% subject-bootstrap CI. B compares the same app with PPG versus ECG HR/RMSSD.\n"
             "Display coverage follows baseline gating; curves show ungated v2 and 50%/25% gate targets.",
             fontsize=8, color=INK2)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(RES / f"fig_brief.{ext}", dpi=200, facecolor=SURFACE)


if __name__ == "__main__":
    main()
