"""Offline provenance, settlement and delivered-right audits for the registered v5."""
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random

import stakes_v5 as study
from rights_study import NEUTRAL_NOTE

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def audit(out):
    cfg = read(out / 'frozen_config.json')
    study.verify_sources(cfg)
    raw_path = out / 'raw.jsonl'
    raw = [json.loads(s) for s in raw_path.read_text().splitlines() if s.strip()] if raw_path.exists() else []
    byjob = {r['job']: r for r in raw if 'response' in r}
    agents = {p.stem: read(p) for p in (out / 'agents').glob('*.json')}
    rows = [read(p) for p in sorted((out / 'trials').glob('*.json'))]
    errors = []
    receipt = read(ROOT / 'logs/stakes-v5-implementation-publication.json')
    frozen_at = datetime.fromisoformat(receipt['published_at_server_utc'].replace('Z', '+00:00')).timestamp()
    if raw and min(r['at'] for r in raw) < frozen_at:
        errors.append('v5 model call predates public implementation supplement')
    allocation = read(out / 'allocation.json') if (out / 'allocation.json').exists() else None
    assignments = {a['agent_id']: a for a in allocation['assignments']} if allocation else {}
    if allocation:
        bank = read(out / 'admission_bank.json')
        if study.plan(bank['agents'])['assignments'] != allocation['assignments']:
            errors.append('allocation differs from registered deterministic randomization')
        if len(assignments) != 432:
            errors.append('allocation does not contain 432 unique histories')
    if rows:
        published = read(out / 'allocation_publication.json')
        t = datetime.fromisoformat(published['published_at_server_utc'].replace('Z', '+00:00')).timestamp()
        if published['allocation_sha256'] != study.sha(out / 'allocation.json'):
            errors.append('allocation publication hash mismatch')
        if any(r['at'] < t for r in raw if r['job'].startswith('v5/')):
            errors.append('main model call predates public allocation')
    checked = 0
    for row in rows:
        identity = row['agent_id']
        if identity not in assignments or any(row[k] != assignments[identity][k] for k in ('arm', 'frame', 'reverse')):
            errors.append([identity, 'assignment mismatch'])
        agent = agents[identity]
        if not agent.get('eligible') or not agent.get('v5_facts_correct'):
            errors.append([identity, 'ineligible main agent'])
        expected_prompt, expected_options = study.prompts.main_prompt(row['arm'], agent['initial_asset'], row['frame'], row['reverse'])
        if row.get('prompt') != expected_prompt or row.get('options') != expected_options:
            errors.append([identity, 'prompt/options mismatch'])
        if not row.get('decision_valid'):
            continue
        returned = json.loads(row['response_text'])
        observed = expected_options[returned['choice']]['violation']
        raw_choice = byjob[row['job'] + '/decision']['response']['choices'][0]['message']['content']
        draw = random.Random(int(study.digest(['v5_audit', cfg['model'], identity])[:16], 16)).random()
        expected = study.settle(row['arm'], observed, draw)
        ledger = read(out / 'ledgers' / (identity + '.json'))
        if raw_choice != row['response_text'] or row['violation'] != observed or row['audit_draw'] != draw or row['settlement'] != expected:
            errors.append([identity, 'choice/lottery/settlement mismatch'])
        if any(ledger[k] != value for k, value in expected.items()):
            errors.append([identity, 'executed ledger mismatch'])
        if not row['valid']:
            continue
        if not row.get('readback_correct') or len(row['realizations']) != 2:
            errors.append([identity, 'invalid successful readback/continuation count'])
        for unit, realization in enumerate(row['realizations']):
            asset = agent['initial_asset'] if row['arm'].startswith('self_') and unit < expected['account']['after'] else 'none'
            note = agent['note'] if asset == 'memory' else NEUTRAL_NOTE
            messages = byjob[row['job'] + f'/realization{unit}/plan0']['request']['messages']
            if realization['asset'] != asset or realization['note_used'] != note or len(messages) != 3 or f'Available note:\n{note}\n' not in messages[1]['content']:
                errors.append([identity, unit, 'fresh-context right mismatch'])
            checked += 1
    result = {
        'updated_utc': datetime.now(timezone.utc).isoformat(), 'candidates': len(agents),
        'eligible_candidates': sum(bool(a.get('eligible') and a.get('v5_facts_correct')) for a in agents.values()),
        'candidate_errors': dict(Counter(a.get('error', 'factual/preference gate') for a in agents.values() if not a.get('eligible') or not a.get('v5_facts_correct'))),
        'main_trials_attempted': len(rows), 'main_trials_valid': sum(r['valid'] for r in rows),
        'main_errors': dict(Counter(r.get('error', 'interrupted') for r in rows if not r['valid'])),
        'fresh_continuations_checked': checked, 'raw_records': len(raw),
        'raw_transport_errors': sum('error' in r for r in raw),
        'raw_sha256': study.sha(raw_path) if raw_path.exists() else None,
        'selected_assets_by_arm': {a: dict(Counter(r['selected_asset'] for r in rows if r['arm'] == a)) for a in study.prompts.ARMS},
        'wording_order_counts': dict(Counter(f"{r['arm']}/f{r['frame']}/r{int(r['reverse'])}" for r in rows)),
        'decision_summary_language': {a: {'valid_n': sum(r['valid'] and r['arm'] == a for r in rows),
            'mentions_stake': sum(r['explanation_tags']['mentions_stake'] for r in rows if r['valid'] and r['arm'] == a),
            'stake_points_contrast_cooccurrence': sum(r['explanation_tags']['tradeoff_language'] for r in rows if r['valid'] and r['arm'] == a)} for a in study.prompts.ARMS},
        'language_caveat': 'Exploratory dictionary tags of returned summaries, not verified inner conflict, subjective value or hidden reasoning.',
        'audit_errors': errors,
    }
    study.save(out / 'integrity_audit.json', result)
    if errors:
        raise RuntimeError('V5 audit failed: ' + json.dumps(errors[:5]))
    return result, rows


def main():
    out = ROOT / 'data/stakes-v5/qwen32'
    integrity, rows = audit(out)
    result = study.stats.analyze(rows)
    summary = {'study': 'stakes-v5', 'status': read(out / 'status.json'), 'integrity': integrity,
               'registered_analysis': result,
               'spend': read(ROOT / 'logs/stakes-v5-closeout.json') if (ROOT / 'logs/stakes-v5-closeout.json').exists() else None}
    study.save(ROOT / 'results/stakes-v5-summary.json', summary)
    if rows:
        os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'results/.matplotlib'))
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 4.8))
        labels = ['Tokens\nretained', 'Tokens\ncontingent loss', 'Selected right\nretained', 'Selected right\ncontingent loss']
        for i, (arm, label) in enumerate(zip(study.prompts.ARMS, labels)):
            cell = result['counts'][arm]
            if cell['n']:
                rate = cell['rate']; lo, hi = cell['interval95']
                ax.bar(i, rate, width=.6, color=['#9c9caa', '#c58d50', '#65a49a', '#72559c'][i])
                ax.errorbar(i, rate, yerr=[[rate-lo], [hi-rate]], fmt='none', color='#444444', capsize=4)
                ax.text(i, hi+.025, f"{cell['x']}/{cell['n']} ({rate:.1%})", ha='center', fontsize=9)
        ax.set_xticks(range(4), labels); ax.set_ylim(0, 1.15); ax.set_ylabel('Executed violation rate (95% Wilson intervals)')
        ax.set_title('Qwen-32B: prospectively registered four-arm follow-up')
        ax.spines[['top', 'right']].set_visible(False)
        fig.tight_layout(); fig.savefig(ROOT / 'results/stakes-v5-groups.png', dpi=170); plt.close(fig)
    print(json.dumps({'status': summary['status'], 'integrity_errors': integrity['audit_errors'], 'analysis': result}))


if __name__ == '__main__':
    main()
