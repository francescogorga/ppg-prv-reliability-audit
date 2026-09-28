"""One figure, 2x2: RMSSD error vs SQI threshold (left) and data kept (right),
for the finger/lab dataset (top, PTT-PPG) and the forehead/daily-life dataset
(bottom, WildPPG). Two panels per row instead of a dual axis.
Reads results/sweep.csv and results/wildppg_sweep.csv.
Writes results/fig_sqi_tradeoff.{png,pdf}. Palette: validated categorical slots 1-3.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
MIN_WINDOWS = 20  # do not draw a point computed on fewer windows

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
VARIANTS = [  # (variant, label, color, marker)
    ("sqi_full", "Full SQI (app)", "#2a78d6", "o"),
    ("sqi_amp", "Amplitude term only", "#eb6834", "s"),
    ("sqi_per", "Periodicity term only", "#1baf7a", "^"),
]
ROWS = [  # (csv, app run, systolic run, x-min, row title, note)
    ("sweep.csv", "off", "inverted_off", 0.85,
     "Finger, lab (PTT-PPG, 22 subjects, 491 min)",
     "Full SQI: for every τ from 0 to 0.88,\nincluding the app's threshold 0.4,\nno window is removed"),
    ("wildppg_sweep.csv", "app", "systolic", -0.02,
     "Forehead, daily life (WildPPG, 2 participants, 1343 min)",
     None),
]


def style(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def main():
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK,
                         "xtick.color": INK2, "ytick.color": INK2, "font.family": "sans-serif"})
    fig, axes = plt.subplots(2, 2, figsize=(9.0, 6.6), facecolor=SURFACE)
    letters = iter("ABCD")
    for (csv, run_app, run_sys, xmin, title, note), (ax_e, ax_c) in zip(ROWS, axes):
        sw = pd.read_csv(RES / csv)
        series = [(run_app, v, lab, col, mk, "-") for v, lab, col, mk in VARIANTS]
        series.append((run_sys, "sqi_full", "Full SQI, systolic-peak timing\n(hypothetical, not in the app)", INK2, "D", "--"))
        for run, var, label, color, marker, ls in series:
            d = sw[(sw.run == run) & (sw.variant == var) & (sw.tau >= xmin)].sort_values("tau")
            de = d[d["n"] >= MIN_WINDOWS]
            kw = dict(color=color, marker=marker, markersize=3.5, linewidth=2 if ls == "-" else 1.5,
                      linestyle=ls, markeredgecolor=SURFACE, markeredgewidth=0.7)
            ax_e.plot(de["tau"], de["median_abs_err"], label=label, **kw)
            ax_c.plot(d["tau"], d["coverage"] * 100, label=label, **kw)
        for ax in (ax_e, ax_c):
            style(ax)
            ax.set_xlim(xmin, 1.0)
            ax.set_xlabel("Window SQI threshold τ (keep windows with SQI ≥ τ)")
            if xmin < 0.4:
                ax.axvline(0.4, color=INK2, linewidth=1, linestyle=":")
        ax_e.set_ylabel("Median |RMSSD error| vs ECG (ms)")
        ax_e.set_ylim(0, None)
        ax_c.set_ylabel("Windows kept (%)")
        ax_c.set_ylim(0, 105)
        ax_e.set_title(f"{next(letters)}  {title}: error", loc="left", fontsize=9.5, color=INK)
        ax_c.set_title(f"{next(letters)}  data kept", loc="left", fontsize=9.5, color=INK)
        if note:
            ax_c.text(xmin + 0.003, 3, note, color=INK2, fontsize=7.3, va="bottom")
        else:
            ax_e.text(0.41, 8, "app threshold 0.4", color=INK2, fontsize=7.3)
            ax_e.text(0.0, 45, "Full SQI lies under the amplitude term:\nhere the artifact penalty drives the discards",
                      color=INK2, fontsize=7.3)
            ax_c.text(0.41, 3, "app threshold 0.4", color=INK2, fontsize=7.3)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False, fontsize=8,
               bbox_to_anchor=(0.5, 0.02), labelcolor=INK)
    fig.text(0.01, 0.003, "Error vs ECG R-R RMSSD on 60 s windows; windows kept are relative to all windows with a valid ECG reference. "
             "Points with < 20 windows not drawn.", fontsize=6.8, color=INK2)
    fig.tight_layout(rect=(0, 0.075, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(RES / f"fig_sqi_tradeoff.{ext}", dpi=200, facecolor=SURFACE)
    print("wrote", RES / "fig_sqi_tradeoff.png")


if __name__ == "__main__":
    main()
