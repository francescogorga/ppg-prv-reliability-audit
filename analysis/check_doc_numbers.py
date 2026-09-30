"""Check result-derived documentation; --write refreshes marked tables/snippets only.

No raw data or scientific dependencies required. Narrative headline checks fail on
stale values rather than rewriting interpretation. Run from any directory.
"""
import argparse
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / 'analysis/results'


def read(name):
    return json.loads((RES / f'{name}.json').read_text())


def stress_table(stress, full=False):
    rows = [('| Stress output vs ECG-based app output | Minutes shown | Cohen’s κ (95% CI) | False alarms |' + (' Misses |' if full else '')),
            '|---|---|---|---|' + ('---|' if full else '')]
    specs = [('finger', 'v1_app', 'Finger — original app'), ('finger', 'v2', 'Finger — systolic v2'),
             ('finger', 'v2_consistency@50%', 'Finger — v2 + consistency, 50% target')]
    if full:
        specs += [('finger', 'v2_consistency@25%', 'Finger — v2 + consistency, 25% target'),
                  ('finger', 'v2_low_estimate@25%', 'Finger — v2 + low estimate, 25% target')]
    specs += [('forehead', 'v1_app', 'Forehead — original app')]
    if full:
        specs += [('forehead', 'v2', 'Forehead — systolic v2')]
    specs += [('forehead', 'v2_consistency@25%', 'Forehead — v2 + consistency, 25% target')]
    for site, key, label in specs:
        r = stress[site]['rules'][key]
        lo, hi = r['kappa_ci95']
        rows.append(f"| {label} | {r['coverage']:.0%} | {r['kappa']:.2f} ({lo:.2f}–{hi:.2f}) | {r['false_alarm']:.0%} |" +
                    (f" {r['miss']:.0%} |" if full else ''))
    return '\n'.join(rows)


def blocks():
    q, c, r, s = map(read, ['quality_models', 'conformal', 'robustness_quality', 'stress_eval'])
    qt = ['| Method | Finger AURC (gap closed) | Error at 50% | AUROC | Forehead AURC (gap closed) | Error at 25% | AUROC |',
          '|---|---|---|---|---|---|---|']
    qt.append(f"| Ungated | {q['finger']['no_gate_median_abs_err']:.1f} | {q['finger']['no_gate_median_abs_err']:.1f} | — | {q['forehead']['no_gate_median_abs_err']:.1f} | {q['forehead']['no_gate_median_abs_err']:.1f} | — |")
    for key, label in [('oracle','Oracle (ECG)'), ('gbm','Gradient boosting'), ('logistic','Logistic regression'),
                       ('tmpl_corr_mean','Beat-template correlation'), ('reject_frac','Rejection count proxy'),
                       ('acc_sd','Accelerometer'), ('sqi_full','App SQI')]:
        vals=[]
        for site, at in [('finger','at50'),('forehead','at25')]:
            v=q[site]['methods'][key]
            vals += [f"{v['aurc']:.1f} ({v['gap_closed']:.0%})", f"{v[at]:.1f}", f"{v['auroc_good']:.2f}" if 'auroc_good' in v else '—']
        qt.append('| '+label+' | '+' | '.join(vals)+' |')
    ct=['| RMSSD interval metric | Finger | Forehead |','|---|---|---|']
    def crow(label, fn): ct.append('| '+label+' | '+' | '.join(fn(c[n], n) for n in ['finger','forehead'])+' |')
    crow('Pooled coverage, adaptive / constant',lambda v,n:f"{v['pooled']['coverage_adaptive']:.1%} / {v['pooled']['coverage_constant']:.1%}")
    crow('Median width, adaptive / constant',lambda v,n:f"{v['pooled']['width_adaptive_median']:.0f} / {v['pooled']['width_constant_median']:.0f} ms")
    crow('Subjects below 80%, adaptive / constant',lambda v,n:f"{v['per_subject_coverage']['subjects_below_80pct_adaptive']} / {v['per_subject_coverage']['subjects_below_80pct_constant']} (adaptive minimum {v['per_subject_coverage']['adaptive_min']:.0%})")
    crow('Width ≤20 ms: retained labelled windows; error; coverage',lambda v,n:f"{v['selective']['width<=20ms']['kept_pct_of_labelled']:.1f}%; {v['selective']['width<=20ms']['median_abs_err']:.1f} ms; {v['selective']['width<=20ms']['interval_coverage']:.0%}")
    crow('Calibrate on other site: adaptive / constant coverage',lambda v,n:f"{c['shift']['calibrate '+('forehead -> test finger' if n=='finger' else 'finger -> test forehead')]['coverage_adaptive']:.1%} / {c['shift']['calibrate '+('forehead -> test finger' if n=='finger' else 'finger -> test forehead')]['coverage_constant']:.1%}")
    rt=['| Retained-value tracking (Spearman; 95% CI) | Finger, 50% | Forehead, 25% |','|---|---|---|']
    for key,label in [('no_gate','Ungated'),('tmpl_corr_mean','Beat-template correlation'),('reject_frac','Rejection count proxy'),('gbm','Gradient boosting'),('gbm_signal_only','GBM excluding selected RR-variability features'),('ppg_rmssd_low','Keep lowest estimates'),('acc_sd','Accelerometer'),('sqi_full','App SQI'),('oracle','Oracle')]:
        vals=[]
        for n in ['finger','forehead']:
            rho=r[n]['no_gate_tracking']['spearman'] if key=='no_gate' else r[n]['pooled_with_tracking'][key]['kept']['spearman_ppg_vs_ecg']
            lo,hi=r[n]['tracking_ci95'][key]
            vals.append(f'{rho:.2f} ({lo:.2f}…{hi:.2f})')
        rt.append('| '+label+' | '+' | '.join(vals)+' |')
    f,h=s['finger']['conformal'],s['forehead']['conformal']
    detail=(f"Empirical score-interval coverage: finger {f['coverage']:.1%}, forehead {h['coverage']:.1%}; "
            f"median width {f['width_median']:.0f} and {h['width_median']:.0f} points. Confident-band outputs occur in "
            f"{f['confident_share']:.0%} and {h['confident_share']:.0%} of evaluated window/split pairs; "
            f"{f['confident_ppg_band_mix']['1']/sum(f['confident_ppg_band_mix'].values()):.1%} and "
            f"{h['confident_ppg_band_mix']['1']/sum(h['confident_ppg_band_mix'].values()):.1%} of those outputs are calm. "
            f"Forehead confident-band agreement is {h['confident_level_matches_ecg_band']:.1%}, versus "
            f"{h['always_calm_agreement_on_confident']:.1%} for always calm on the same subset; "
            f"κ = {h['confident_kappa']:.2f}, with {h['confident_miss']:.0%} of non-calm reference bands missed.")
    brief=(f"Median score-interval widths were {f['width_median']:.0f} points on finger and "
           f"{h['width_median']:.0f} (the full scale) on forehead. Confident bands covered "
           f"{f['confident_share']:.0%}/{h['confident_share']:.0%} of evaluated window/split pairs, almost all calm. "
           f"Forehead agreement was {h['confident_level_matches_ecg_band']:.0%}, near always-calm "
           f"({h['always_calm_agreement_on_confident']:.0%}); κ = {h['confident_kappa']:.2f}.")
    return {'STRESS_TABLE':stress_table(s),'STRESS_FULL_TABLE':stress_table(s,True),'QUALITY_TABLE':'\n'.join(qt),
            'CONFORMAL_TABLE':'\n'.join(ct),'TRACKING_TABLE':'\n'.join(rt),'STRESS_CONFORMAL':detail,
            'STRESS_UNCERTAINTY_BRIEF':brief}


def check_historical_tables(text):
    """Verify numeric cells in the translated original result tables."""
    a, w, o, c = map(read, ['summary', 'wildppg_summary', 'oracle_check', 'sqi_calibration'])
    def row(label, expected):
        line = next(x for x in text.splitlines() if x.startswith('| '+label+' |'))
        cells = line[len('| '+label+' |'):].replace('−', '-').replace('–', ' ')
        got = [float(x) for x in re.findall(r'-?\d+(?:\.\d+)?', cells)]
        assert got == expected, f'Stale historical row {label}: {got} != {expected}'
    def r(x, n=1): return float(f'{x:.{n}f}')
    v=a['no_filter']; ci=a['bootstrap_median_abs_err']['none']['ci95']
    row('App pipeline, no gate', [r(v['coverage']*100),r(v['median_abs_err']),*map(r,ci),r(v['ba_bias']),r(v['ba_loa_low']),r(v['ba_loa_high']),r(v['pearson_r'],2)])
    row('Window SQI ≥ 0.4', [r(v['coverage']*100),r(v['median_abs_err']),0,0,r(v['pearson_r'],2)])
    v=a['in_loop_gate_as_app']['0.4']
    row('In-loop SQI ≥ 0.4, as in app',[r(v['coverage']*100),r(v['median_abs_err']),*[r(x,2) for x in a['bootstrap_median_abs_err']['in_loop_0.4']['reduction_vs_none_ci95']],r(v['ba_bias']),r(v['pearson_r'],2)])
    for t in ['0.96','0.97','0.98']:
        v=a['high_threshold_post_hoc'][t]
        row('SQI ≥ '+t+', post hoc'+(', 12 subjects' if t=='0.98' else ''),[r(v['coverage']*100),r(v['median_abs_err']),*map(r,a['bootstrap_median_abs_err'][f'sqi_full>={t} (post hoc)']['ci95'])])
    vals=[a['high_threshold_post_hoc'][t] for t in ['0.96','0.97','0.98']]
    row('Accelerometer at the three matched coverages',[*[r(v['coverage']*100,0) for v in vals],*[r(v['motion_gate_same_coverage']['median_abs_err']) for v in vals]])
    v=a['robustness']['inverted_input_no_filter (not the app)']
    row('Hypothetical inverted-input systolic timing, ungated',[r(v['coverage']*100),r(v['median_abs_err']),*map(r,a['bootstrap_median_abs_err']['inverted_input_none (not the app)']['ci95']),r(v['ba_bias']),r(v['ba_loa_low']),r(v['ba_loa_high']),r(v['pearson_r'],2)])
    v=a['robustness']['sensor2_no_filter']
    row('Sensor 2 (`pleth_4`), ungated',[r(v['coverage']*100),r(v['median_abs_err']),r(v['pearson_r'],2)])
    v=w['no_filter']; row('App IR light polarity, ungated',[r(v['coverage']*100),r(v['median_abs_err']),*map(r,w['bootstrap_median_abs_err']['none']['ci95']),r(v['ba_bias']),r(v['pearson_r'],2)])
    # Forehead uses the same window-SQI label; select its section explicitly.
    text=text[text.index('## 8.'):]
    for key,label,ci in [('post_hoc_app_threshold','Window SQI ≥ 0.4','sqi_full>=0.4'),('in_loop_0_4','In-loop SQI ≥ 0.4','in_loop_0.4')]:
        v=w[key]['sqi_full'] if key=='post_hoc_app_threshold' else w[key]
        row(label,[r(v['coverage']*100),r(v['median_abs_err']),*map(r,w['bootstrap_median_abs_err'][ci]['reduction_vs_none_ci95'])])
    for key,label in [('dropped_by_sqi_0_4','Discarded by that SQI gate'),('app_100hz_no_filter','App run resampled to 100 Hz'),('green_no_filter','Green, light polarity')]:
        v=w[key]; row(label,[r(v['coverage']*100),r(v['median_abs_err'])])
    v=w['systolic_no_filter']; row('Systolic IR timing, offline',[r(v['coverage']*100),r(v['median_abs_err']),*map(r,w['bootstrap_median_abs_err']['systolic_none (not the app)']['ci95'])])
    for gate,label in [('sqi','SQI ≥ 0.96 / 0.97, post hoc'),('motion_same_coverage','Accelerometer at matched coverage')]:
        vals=[w['high_threshold_post_hoc'][t][gate] for t in ['0.96','0.97']]
        row(label,[*[r(v['coverage']*100) for v in vals],*[r(v['median_abs_err']) for v in vals]])
    for site,label in [('finger_lab','Finger'),('forehead_daily_life','Forehead')]:
        for key,version in [('app','v1'),('v2, systolic peak (not in app)','v2')]:
            v=o[site][key]; at=v['at_coverage']['50%']
            row(label+' '+version+(', two participants' if label=='Forehead' else ''),[*[r(at[k]) for k in ['oracle','sqi_full','sqi_per','motion']],r(v['no_gate_median_abs_err']),r(v['good_windows_pct_of_computable']['abs_err<=5ms'])])
    for t in [50,25,75]:
        for gate,label in [('sqi_full','SQI / periodicity' if t==50 else 'SQI'),('motion','ACC')]:
            v=c['finger_split_half']['v2'][f'{gate}@{t}%']
            cv,err=v['test_coverage_pct'],v['test_median_abs_err_ms']
            row(f'{t}% | {label}',[r(cv[1],0),r(cv[0],0),r(cv[2],0),r(err[1]),r(err[0]),r(err[2]),r(v['oracle_same_coverage_ms'][1])])


def main(write=False):
    data=blocks()
    count=0
    for path in [ROOT/'README.md', ROOT/'brief/brief_draft.md', ROOT/'analysis/README.md']:
        text=path.read_text()
        for key,value in data.items():
            pattern=rf'<!-- BEGIN {key} -->\n.*?\n<!-- END {key} -->'
            if not re.search(pattern,text,re.S):
                continue
            expected=f'<!-- BEGIN {key} -->\n{value}\n<!-- END {key} -->'
            if write:
                text=re.sub(pattern,lambda m:expected,text,flags=re.S)
            else:
                assert re.search(pattern,text,re.S).group()==expected, f'Stale {key} in {path}'
            count+=1
        if write: path.write_text(text)
    a, q, r, v, f = map(read,['summary','quality_models','robustness_quality','rpeak_validation','fiducial_check'])
    root=(ROOT/'README.md').read_text(); brief=(ROOT/'brief/brief_draft.md').read_text()
    # Headline measurements are recomputed independently from committed CSV columns.
    from statistics import median
    for name in ['finger','forehead']:
        rows=list(csv.DictReader((RES/f'features_{name}.csv').open()))
        lab=[x for x in rows if x['ref_ok']=='True' and x['rmssd_v2']]
        err=median(abs(float(x['rmssd_v2'])-float(x['ref_rmssd'])) for x in lab)
        assert abs(err-q[name]['no_gate_median_abs_err'])<1e-10
        for x in rows:
            npk,na=float(x['n_peaks']),float(x['n_accepted'])
            expected=max(0,min(1,1-na/max(npk,1))) if npk else 1
            assert float(x['reject_frac'])==expected
    # Explicit source-to-prose checks; table checks above cover every displayed CI.
    claims={
        'v1 error':f"{a['no_filter']['median_abs_err']:.1f}",
        'reference median':f"{a['ref_rmssd_ms']['median']:.1f}",
        'v2 error':f"{a['v2_no_filter (not the app)']['median_abs_err']:.1f}",
        'forehead error':f"{q['forehead']['no_gate_median_abs_err']:.1f}",
        'validation timing':f"{v['timing_abs_err_ms_median']:.2f}",
        'validation RMSSD':f"{v['cleaned_detected_vs_manual']['abs_diff_ms_median']:.2f}",
    }
    for label,value in claims.items():
        assert value in root and value in brief, f'Missing or stale {label}: expected {value}'
    for site in ['finger','forehead']:
        assert str(q[site]['subjects']) in root and str(q[site]['subjects']) in brief
    for key in ['ppg_rmssd_low','tmpl_corr_mean']:
        value=f"{r['forehead']['pooled_with_tracking'][key]['kept']['spearman_ppg_vs_ecg']:.2f}"
        assert value in root and value in brief
    for key in ['tmpl_corr_mean','sqi_full']:
        k=r['finger']['pooled_with_tracking'][key]['kept']
        assert f"{k['median_abs_err']:.1f}" in brief and f"{k['spearman_ppg_vs_ecg']:.2f}" in brief
    assert f"{f['raw_as_app']['all']['lag_iqr_ms']:.1f}" in brief
    assert f"{f['raw_as_app']['all']['beats_missed_pct']:.1f}" in brief
    commit=re.search(r'^commit: ([a-f0-9]+)',(RES/'terra_schema_check.txt').read_text(),re.M).group(1)
    assert commit in root and commit in brief and commit in (ROOT/'analysis/README.md').read_text()
    check_historical_tables((ROOT/'analysis/README.md').read_text())
    print(f'PASS: {count} generated documentation blocks plus historical tables, headline values, source CSV medians, all count proxies, schema revision')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    main(parser.parse_args().write)
