"""Brief figure: for each gate, the error of the windows it keeps (x) against whether the
kept RMSSD still follows the ECG RMSSD (y, Spearman, 95% subject-bootstrap CI).
Good gates are bottom-left in error and high in tracking. Reads results/robustness_quality.json.
Writes results/fig_tracking.{png,pdf}.
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RES = Path(__file__).resolve().parent / "results"
SURFACE, INK, INK2, GRID, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#8f8e89"
STYLE = {  # method: (label, colour, marker)
    "oracle": ("Oracle (needs ECG)", INK, "*"),
    "tmpl_corr_mean": ("Beat-template correlation", "#1baf7a", "o"),
    "reject_frac": ("Rejected-beat share", MUTED, "o"),
    "gbm": ("Gradient boosting, all features", MUTED, "s"),
    "gbm_signal_only": ("Gradient boosting, signal-only", MUTED, "D"),
    "ppg_rmssd_low": ("Keep lowest HRV estimates", "#eb6834", "v"),
    "acc_sd": ("Accelerometer", MUTED, "^"),
    "sqi_full": ("App SQI", "#2a78d6", "o"),
    "no_gate": ("No gate", MUTED, "x"),
}


def main():
    R = json.load(open(RES / "robustness_quality.json"))
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.3), facecolor=SURFACE)
    titles = {"finger": "A  Finger, lab — keep 50% of windows",
              "forehead": "B  Forehead, daily life — keep 25% of windows"}
    for ax, name in zip(axes, ("finger", "forehead")):
        r = R[name]
        ax.set_facecolor(SURFACE)
        ax.grid(True, color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ci = r["tracking_ci95"]
        for m, (lab, col, mk) in STYLE.items():
            if m == "no_gate":
                x, y = r["no_gate_tracking"]["median_abs_err"], r["no_gate_tracking"]["spearman"]
            else:
                k = r["pooled_with_tracking"][m]["kept"]
                x, y = k["median_abs_err"], k["spearman_ppg_vs_ecg"]
            lo, hi = ci[m]
            ax.errorbar(x, y, yerr=[[y - lo], [hi - y]], fmt="none", ecolor=col, alpha=0.45, linewidth=1.2, capsize=2)
            ax.scatter(x, y, color=col, marker=mk, s=70 if m in ("tmpl_corr_mean", "ppg_rmssd_low", "sqi_full", "oracle") else 38,
                       edgecolors=None if mk == "x" else SURFACE, linewidths=0.8, zorder=3, label=lab)
        short = {"oracle": "oracle", "tmpl_corr_mean": "beat-template\ncorrelation", "ppg_rmssd_low": "keep lowest\nestimates",
                 "sqi_full": "app SQI", "no_gate": "no gate"}
        offs = {"finger": {"oracle": (8, 4), "tmpl_corr_mean": (-58, -12), "ppg_rmssd_low": (8, -6), "sqi_full": (8, -2), "no_gate": (-44, 8)},
                "forehead": {"oracle": (-38, 6), "tmpl_corr_mean": (10, 8), "ppg_rmssd_low": (-50, -16), "sqi_full": (8, -2), "no_gate": (-44, 8)}}
        for m, txt in short.items():
            if m == "no_gate":
                x, y = r["no_gate_tracking"]["median_abs_err"], r["no_gate_tracking"]["spearman"]
            else:
                k = r["pooled_with_tracking"][m]["kept"]
                x, y = k["median_abs_err"], k["spearman_ppg_vs_ecg"]
            ax.annotate(txt, (x, y), xytext=offs[name][m], textcoords="offset points", fontsize=7.5,
                        color=STYLE[m][1] if m != "no_gate" else INK2)
        ax.set_xlabel("Median |RMSSD error| of kept windows (ms)")
        ax.set_ylabel("Kept RMSSD vs ECG RMSSD (Spearman)")
        ax.set_title(titles[name], loc="left", fontsize=9.5, color=INK)
        ax.set_xlim(*{"finger": (2, 19.5), "forehead": (10, 95)}[name])
        ax.set_ylim(-0.25, 1.0)
    h, lab = axes[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=5, frameon=False, fontsize=7.8, bbox_to_anchor=(0.5, 0.02))
    fig.text(0.01, 0.003, "v2 pipeline; scores from leave-one-subject-out models; bars: 95% bootstrap CI over subjects. "
             "Better = left (lower error) and up (kept values follow the truth).", fontsize=7, color=INK2)
    fig.tight_layout(rect=(0, 0.13, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(RES / f"fig_tracking.{ext}", dpi=200, facecolor=SURFACE)


if __name__ == "__main__":
    main()
