"""How much of the app's stress output survives PPG error, and what helps?

Compares, minute by minute, the stress level the app would show with PPG-derived HR/HRV
against the level it would show with ECG-derived HR/HRV (build_stress.py). Levels:
calm / aroused / stressed. Only non-baseline minutes with a reliable ECG reference count.

Display rules (the stress values are the app's; the rule only decides what is shown):
  v1_app            the app as deployed
  v2                v2 pipeline, always shown
  v2_consistency    v2, shown only if the minute's beat-template correlation passes a
                    threshold AND the session's baseline minute passed it too (no
                    calibration on bad data). The threshold is chosen on the OTHER
                    subjects to keep a target share of their minutes (leave-one-subject-out).
  v2_low_estimate   same, but ranking by the lowest RMSSD estimate (the "trap" gate)
Metrics on shown minutes: agreement, Cohen's kappa, false alarms (shows aroused/stressed
when the ECG-based level is calm), misses (shows calm when it is aroused/stressed),
|score difference|; coverage = shown / evaluable minutes. 95% CIs: bootstrap over subjects.

Uncertainty: split-conformal intervals on the stress score (adaptive width from gradient
boosting on the 24 features plus the score itself); a level is "confident" when the whole
interval lies in one level band (<35, 35-65, >=65; the app's entry thresholds).
Output: results/stress_eval.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

from conformal import conformal_q
from features import FEATURES
from quality_models import gbm
from run_analysis import SEED

RES = Path(__file__).resolve().parent / "results"
TARGETS = (0.50, 0.25)
N_BOOT = 1000
ALPHA = 0.10
REPEATS = 10
KEY = {"finger": ["record", "t0"], "forehead": ["subject", "t0"]}


def load(name):
    s = pd.read_csv(RES / f"stress_{name}.csv")
    f = pd.read_csv(RES / f"features_{name}.csv")
    f["subject"] = f["subject"].astype(str)
    s["subject"] = s["subject"].astype(str)
    d = s.merge(f[KEY[name] + ["ref_ok", "ppg_rmssd"] + [c for c in FEATURES if c != "ppg_rmssd"]],
                on=KEY[name], how="left", validate="one_to_one")
    # baseline-minute quality of each session, attached to every minute of the session
    b = d[d["baseline_window"]][["record", "session", "tmpl_corr_mean", "ppg_rmssd"]].rename(
        columns={"tmpl_corr_mean": "base_tmpl", "ppg_rmssd": "base_rmssd"})
    d = d.merge(b, on=["record", "session"], how="left")
    ev = d[~d["baseline_window"] & d["ref_ok"].fillna(False).astype(bool) & (d["level_ecg"] > 0)].reset_index(drop=True)
    return ev


def metrics(ref, shown, score_ref, score_shown):
    n = len(ref)
    if n < 10:
        return dict(n=n)
    calm = ref == 1
    return dict(
        n=int(n), agreement=float(np.mean(ref == shown)),
        kappa=float(cohen_kappa_score(ref, shown, labels=[1, 2, 3])),
        false_alarm=float(np.mean(shown[calm] > 1)) if calm.any() else None,
        miss=float(np.mean(shown[~calm] == 1)) if (~calm).any() else None,
        score_mae=float(np.mean(np.abs(score_ref - score_shown))),
        band_agreement=float(np.mean(band(score_ref) == band(score_shown))),
        ref_level_mix={int(k): int(v) for k, v in zip(*np.unique(ref, return_counts=True))},
    )


def gate_masks(ev, feature, higher_better, target):
    """LOSO threshold: keep `target` of the other subjects' evaluable minutes."""
    keep = np.zeros(len(ev), bool)
    x = ev[feature].to_numpy(dtype=float) * (1 if higher_better else -1)
    xb = ev["base_tmpl" if feature == "tmpl_corr_mean" else "base_rmssd"].to_numpy(dtype=float) * (1 if higher_better else -1)
    for s in ev["subject"].unique():
        te = (ev["subject"] == s).to_numpy()
        other = x[~te]
        other = other[np.isfinite(other)]
        thr = np.quantile(other, 1 - target) if len(other) else np.inf
        keep[te] = np.nan_to_num(x[te], nan=-np.inf) >= thr
        keep[te] &= np.nan_to_num(xb[te], nan=-np.inf) >= thr
    return keep


def evaluate(ev, rng):
    ref, sref = ev["level_ecg"].to_numpy(int), ev["score_ecg"].to_numpy(float)
    rules = {"v1_app": ("level_v1_app", "score_v1_app", np.ones(len(ev), bool)),
             "v2": ("level_v2", "score_v2", np.ones(len(ev), bool))}
    for t in TARGETS:
        rules[f"v2_consistency@{int(t * 100)}%"] = ("level_v2", "score_v2", gate_masks(ev, "tmpl_corr_mean", True, t))
        rules[f"v2_low_estimate@{int(t * 100)}%"] = ("level_v2", "score_v2", gate_masks(ev, "ppg_rmssd", False, t))
    out = {}
    subj = ev["subject"].to_numpy()
    subjects = np.unique(subj)
    by = {s: np.flatnonzero(subj == s) for s in subjects}
    for name, (lc, sc, mask) in rules.items():
        lv = ev[lc].to_numpy(dtype=float)
        shown = mask & (lv > 0)
        r = metrics(ref[shown], lv[shown].astype(int), sref[shown], ev[sc].to_numpy(float)[shown])
        r["coverage"] = float(shown.mean())
        boot_k, boot_a, boot_f = [], [], []
        for _ in range(N_BOOT):
            idx = np.concatenate([by[s] for s in rng.choice(subjects, len(subjects), replace=True)])
            i2 = idx[shown[idx]]
            if len(i2) < 10:
                continue
            boot_k.append(cohen_kappa_score(ref[i2], lv[i2].astype(int), labels=[1, 2, 3]))
            boot_a.append(np.mean(ref[i2] == lv[i2]))
            c = ref[i2] == 1
            boot_f.append(np.mean(lv[i2][c] > 1) if c.any() else np.nan)
        r["kappa_ci95"] = [float(np.nanpercentile(boot_k, 2.5)), float(np.nanpercentile(boot_k, 97.5))]
        r["agreement_ci95"] = [float(np.nanpercentile(boot_a, 2.5)), float(np.nanpercentile(boot_a, 97.5))]
        r["false_alarm_ci95"] = [float(np.nanpercentile(boot_f, 2.5)), float(np.nanpercentile(boot_f, 97.5))]
        out[name] = r
    return out


def band(x):
    return np.where(x >= 65, 3, np.where(x >= 35, 2, 1))


def conformal(ev, rng):
    X = ev[FEATURES].copy()
    X["score_v2"] = ev["score_v2"]
    ok = (ev["level_v2"] > 0).to_numpy()
    d, X = ev[ok].reset_index(drop=True), X[ok].reset_index(drop=True)
    err = np.abs(d["score_v2"] - d["score_ecg"]).to_numpy()
    subjects = d["subject"].unique()
    cov, width, conf, conf_ok, conf_ppg, conf_ecg = [], [], [], [], [], []
    for s in subjects:
        te = (d["subject"] == s).to_numpy()
        others = np.array([x for x in subjects if x != s])
        for _ in range(REPEATS):
            perm = rng.permutation(others)
            ntr = int(round(len(perm) * 2 / 3))
            tr = d["subject"].isin(perm[:ntr]).to_numpy()
            ca = d["subject"].isin(perm[ntr:]).to_numpy()
            m = gbm().fit(X[tr], np.log1p(err[tr]))
            sig_c = np.expm1(m.predict(X[ca])) + 1.0
            sig_t = np.expm1(m.predict(X[te])) + 1.0
            sc = np.sort(err[ca] / sig_c)
            q = conformal_q(sc, alpha=ALPHA)
            lo = np.clip(d["score_v2"].to_numpy()[te] - q * sig_t, 0, 100)
            hi = np.clip(d["score_v2"].to_numpy()[te] + q * sig_t, 0, 100)
            cov.append(err[te] <= q * sig_t)
            width.append(hi - lo)
            c = band(lo) == band(hi)                     # interval inside one level band
            conf.append(c)
            conf_ok.append(band(lo)[c] == band(d["score_ecg"].to_numpy()[te])[c])
            conf_ppg.append(band(lo)[c])
            conf_ecg.append(band(d["score_ecg"].to_numpy()[te])[c])
    cov, width, conf = np.concatenate(cov), np.concatenate(width), np.concatenate(conf)
    conf_ok = np.concatenate(conf_ok)
    cp, ce = np.concatenate(conf_ppg), np.concatenate(conf_ecg)
    all_ecg = band(d["score_ecg"].to_numpy())
    return dict(target=1 - ALPHA, coverage=float(cov.mean()), width_median=float(np.median(width)),
                confident_share=float(conf.mean()),
                confident_level_matches_ecg_band=float(conf_ok.mean()) if conf_ok.size else None,
                confident_kappa=float(cohen_kappa_score(ce, cp, labels=[1, 2, 3])) if cp.size else None,
                confident_ecg_band_mix={int(k): int(v) for k, v in zip(*np.unique(ce, return_counts=True))},
                confident_ppg_band_mix={int(k): int(v) for k, v in zip(*np.unique(cp, return_counts=True))},
                all_minutes_ecg_band_mix={int(k): int(v) for k, v in zip(*np.unique(all_ecg, return_counts=True))},
                always_calm_agreement_on_confident=float(np.mean(ce == 1)) if ce.size else None,
                confident_false_alarm=float(np.mean(cp[ce == 1] > 1)) if (ce == 1).any() else None,
                confident_miss=float(np.mean(cp[ce > 1] == 1)) if (ce > 1).any() else None,
                note="confident = the whole interval lies in one band (<35, 35-65, >=65)")


def main():
    rng = np.random.default_rng(SEED)
    out = {}
    for name in ("finger", "forehead"):
        if not (RES / f"stress_{name}.csv").exists():
            continue
        ev = load(name)
        out[name] = dict(evaluable_minutes=int(len(ev)), subjects=int(ev["subject"].nunique()),
                         rules=evaluate(ev, rng), conformal=conformal(ev, rng))
    (RES / "stress_eval.json").write_text(json.dumps(out, indent=2))
    for name, r in out.items():
        print("==", name, "minutes", r["evaluable_minutes"], "subjects", r["subjects"])
        for k, v in r["rules"].items():
            f = lambda x: "-" if x is None else f"{x:.2f}"
            print(f"  {k:24s} cov {v['coverage']*100:5.1f}% | band agree {f(v.get('band_agreement'))} | agree {f(v.get('agreement'))} kappa {f(v.get('kappa'))} "
                  f"[{v['kappa_ci95'][0]:.2f},{v['kappa_ci95'][1]:.2f}] | FA {f(v.get('false_alarm'))} miss {f(v.get('miss'))} | MAE {f(v.get('score_mae'))} | n {v.get('n')} mix {v.get('ref_level_mix')}")
        print("  conformal", r["conformal"])


if __name__ == "__main__":
    main()
