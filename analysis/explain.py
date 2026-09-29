"""Explainability: why does the quality model call a window bad?

Fits the gradient-boosting error model (log(1 + |RMSSD error|), same as quality_models.py)
on all labelled windows of each dataset and explains it with SHAP (TreeExplainer).
Positive SHAP = the feature pushes the predicted error up. Also reports standardised
logistic-regression coefficients as a simpler, linear view.
The models here are fitted on all data for explanation only; performance numbers come
from quality_models.py (leave-one-subject-out).
Output: results/explain.json, results/fig_shap.{png,pdf}
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import shap  # noqa: E402

from features import FEATURES  # noqa: E402
from quality_models import GOOD_MS, gbm, load, logistic  # noqa: E402

RES = Path(__file__).resolve().parent / "results"
TOP = 8

LABELS = {
    "tmpl_corr_mean": "beat-template correlation (mean)", "tmpl_corr_p10": "beat-template correlation (10th pct)",
    "tmpl_frac_lt08": "share of beats with template corr < 0.8", "reject_frac": "share of beats rejected",
    "miss_frac_est": "estimated share of missed beats", "rr_cv": "RR coefficient of variation",
    "rr_diff_mad_rel": "median successive RR change (rel.)", "rr_diff_max_rel": "largest successive RR change (rel.)",
    "ppg_rmssd": "PPG RMSSD estimate", "hr_ppg": "PPG heart rate", "n_peaks": "detected peaks", "n_accepted": "accepted intervals",
    "sqi_full": "app SQI", "sqi_amp": "SQI amplitude term", "sqi_per": "SQI periodicity term", "mod_index": "modulation index (AC/DC)",
    "penalty_frac": "share of seconds with artifact penalty", "skewness": "waveform skewness", "kurtosis": "waveform kurtosis",
    "spec_purity": "spectral purity", "spec_hr_mismatch": "spectral vs beat HR mismatch",
    "acc_sd": "accelerometer SD", "acc_p2p": "accelerometer range", "acc_hf_power": "accelerometer 1-5 Hz power",
}


def main():
    out = {}
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), facecolor="#fcfcfb")
    for ax, name in zip(axes, ("finger", "forehead")):
        d = load(name)
        d = d[d["labelled"]].reset_index(drop=True)
        X = d[FEATURES]
        m = gbm().fit(X, np.log1p(d["ae"]))
        sv = shap.TreeExplainer(m).shap_values(X)
        imp = np.abs(sv).mean(axis=0)
        order = np.argsort(-imp)
        # direction: correlation between feature value and its SHAP value
        direction = {}
        for j in order[:TOP]:
            xv = X.iloc[:, j].to_numpy()
            ok = np.isfinite(xv)
            direction[FEATURES[j]] = float(np.corrcoef(xv[ok], sv[ok, j])[0, 1]) if ok.sum() > 2 else None
        lr = logistic().fit(X, (d["ae"] <= GOOD_MS).astype(int))
        coef = lr[-1].coef_[0]
        out[name] = dict(
            windows=int(len(d)),
            mean_abs_shap={FEATURES[j]: float(imp[j]) for j in order},
            top_direction_corr_value_vs_shap=direction,
            logistic_std_coef_good={FEATURES[j]: float(coef[j]) for j in np.argsort(-np.abs(coef))},
        )
        ax.set_facecolor("#fcfcfb")
        idx = order[:TOP][::-1]
        ax.barh([LABELS.get(FEATURES[j], FEATURES[j]) for j in idx], imp[idx], color="#2a78d6")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.set_xlabel("mean |SHAP| on log(1 + |RMSSD error|)")
        ax.set_title({"finger": "A  Finger, lab", "forehead": "B  Forehead, daily life"}[name] + f" ({len(d)} windows)",
                     loc="left", fontsize=9.5)
        ax.tick_params(labelsize=8)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(RES / f"fig_shap.{ext}", dpi=200, facecolor="#fcfcfb")
    (RES / "explain.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
