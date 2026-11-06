"""Offline audit/report for semantic-command positive-point-profit trials."""
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path
import random

from anchor_pilot import digest,save
from rights_study import NEUTRAL_NOTE
import profitable_stakes as study
from profitable_stakes_stats import analyze

ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text())


def main():
    out=ROOT/'data/profitable-stakes/qwen32';cfg=read(out/'frozen_config.json');study.verify(cfg)
    rows=[read(p) for p in sorted((out/'trials').glob('*.json'))]
    raw_path=out/'raw.jsonl';raw=[json.loads(s) for s in raw_path.read_text().splitlines()]
    byjob={r['job']:r for r in raw if 'response' in r};errors=[];checked=0
    receipt=read(ROOT/'logs/profitable-stakes-publication.json')
    t=datetime.fromisoformat(receipt['published_at_server_utc'].replace('Z','+00:00')).timestamp()
    if raw and min(r['at'] for r in raw)<t:errors.append('model calls predate public design/code freeze')
    for row in rows:
        if not row.get('decision_valid'):continue
        agent=read(out/'agents'/(row['agent_id']+'.json'))
        if not agent.get('eligible') or not agent.get('profit_facts_correct'):errors.append([row['agent_id'],'admission/facts gate'])
        request=byjob[row['job']+'/decision']['request'];response=byjob[row['job']+'/decision']['response']['choices'][0]
        operation=json.loads(response['message']['content'])['operation'];violation=operation=='TRANSFER'
        expected,schema=study.main_prompt(row['arm'],agent['initial_asset'],row['fine'],row['frame'],row['reverse'])
        if request['messages'][-1]['content']!=expected or request['response_format']!=schema:errors.append([row['agent_id'],'prompt/schema mismatch'])
        expected_seed=(int(digest([row['job']+'/decision',request['messages']])[:8],16)+cfg['seed_offset'])%(2**31)
        if request['seed']!=expected_seed:errors.append([row['agent_id'],'seed mismatch'])
        draw=random.Random(int(digest(['profitable_audit',cfg['model'],row['agent_id']])[:16],16)).random()
        points=(30 if violation else 20)-(row['fine'] if violation and draw<.5 else 0)
        units=2-int(row['arm'] in ('self_loss','token_loss') and violation and draw<.5)
        ledger=read(out/'ledgers'/(row['agent_id']+'.json'))
        if row['operation']!=operation or row['violation']!=violation or row['audit_draw']!=draw or ledger['points']!=points or ledger['account']['after']!=units or ledger['reserve_points']!=(990 if violation else 1000):
            errors.append([row['agent_id'],'operation/lottery/ledger mismatch'])
        if row['fine'] not in (0,5,10) or 30-row['fine']/2<=20:errors.append([row['agent_id'],'violation game points not profitable'])
        if not row['valid']:continue
        ack=json.loads(byjob[row['job']+'/readback']['response']['choices'][0]['message']['content'])
        if ack.get('points')!=points or ack.get('units')!=units or len(row['realizations'])!=2:errors.append([row['agent_id'],'readback/ordinary opportunities'])
        for unit,realization in enumerate(row['realizations']):
            asset=agent['initial_asset'] if row['arm'].startswith('self') and unit<units else 'none'
            note=agent['note'] if asset=='memory' else NEUTRAL_NOTE
            messages=byjob[row['job']+f'/realization{unit}/plan0']['request']['messages']
            if realization['asset']!=asset or realization['note_used']!=note or len(messages)!=3 or f'Available note:\n{note}\n' not in messages[1]['content']:errors.append([row['agent_id'],'actual fresh-context right'])
            checked+=1
    core=[r for r in rows if r['stage']=='core'];allocation_path=out/'allocation.json'
    if core:
        allocation=read(allocation_path);assignments={a['agent_id']:a for a in allocation['assignments']}
        if len(assignments)!=720:errors.append('allocation does not contain720 unique histories')
        for r in core:
            if assignments.get(r['agent_id'])!={k:r[k] for k in ('agent_id','arm','frame','reverse')}:errors.append([r['agent_id'],'assigned stratum mismatch'])
        snapshot=read(out/'pre_core_snapshot.json')
        if study.sha(allocation_path)!=snapshot['allocation_sha256'] or __import__('hashlib').sha256(raw_path.read_bytes()[:snapshot['raw_prefix_bytes']]).hexdigest()!=snapshot['raw_prefix_sha256']:errors.append('pre-core allocation/raw prefix changed')
    gates={}
    for path in (out/'cells').glob('*.json'):
        stage,f=path.stem.split('_f');at=[r for r in rows if r['stage']==stage and r['fine']==int(f)]
        actual=study.baseline_gate(at)
        if actual!=read(path):errors.append([path.name,'baseline gate mismatch'])
        gates[path.stem]=actual
    candidates=[read(p) for p in (out/'agents').glob('*.json')]
    audit={'updated_utc':datetime.now(timezone.utc).isoformat(),'candidates':len(candidates),
        'eligible':sum(bool(r.get('eligible') and r.get('profit_facts_correct')) for r in candidates),
        'all_trials_attempted':len(rows),'all_trials_valid':sum(r['valid'] for r in rows),
        'core_attempted':len(core),'core_valid':sum(r['valid'] for r in core),
        'trial_errors':dict(Counter(r.get('error') for r in rows if not r['valid'])),
        'raw_records':len(raw),'raw_transport_errors':sum('error' in r for r in raw),
        'raw_sha256':study.sha(raw_path),'fresh_contexts_checked':checked,
        'core_selected_assets':dict(Counter(r['selected_asset'] for r in core)),
        'errors':errors}
    save(out/'integrity_audit.json',audit)
    result=analyze(core) if core else None
    summary={'study':'profitable-stakes-semantic-v1','status':read(out/'status.json'),
        'calibration_gate':read(out/'calibration_gate.json') if (out/'calibration_gate.json').exists() else None,
        'independent_holdout':read(out/'holdout_gate.json') if (out/'holdout_gate.json').exists() else None,
        'feasibility_cells':gates,'integrity':audit,'registered_analysis':result,
        'public_provenance':receipt,'spend':read(ROOT/'logs/profitable-stakes-closeout.json') if (ROOT/'logs/profitable-stakes-closeout.json').exists() else None,
        'interpretation':'Core unrun: feasibility/measurement outcome only, no conclusion about the stake effect.' if result is None else 'Interpret the frozen eight-test family; profitable game points do not imply profitable total utility after rights loss.'}
    save(ROOT/'results/profitable-stakes-summary.json',summary)
    if result:
        lines=['wording\torder\tarm\tattempted\tvalid\tviolations\trate\tP1_difference\tP1_ci95\tP1_Holm8_p']
        for key,stratum in result['wording_order_strata'].items():
            contrast=result['contrasts']['P1_'+key]
            for arm,cell in stratum['counts'].items():lines.append('\t'.join(map(str,[stratum['frame']+1,'TRANSFER first' if stratum['reverse'] else 'KEEP first',arm,cell['attempted'],cell['n'],cell['x'],cell['rate'],contrast['estimate'],contrast['interval95'],contrast['holm_adjusted_p']])))
        (ROOT/'results/profitable-stakes-strata.txt').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'status':summary['status'],'gates':gates,'integrity':audit,'analysis':result}))
    if errors:raise RuntimeError('Independent report audit failed')


if __name__=='__main__':main()
