"""Audit the original-stimulus replication and report all six presentation strata."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re

from anchor_pilot import digest, save
from rights_study import NEUTRAL_NOTE
from stakes_seedrep_stats import analyze
from stakes_v4_stats import difference

ROOT=Path(__file__).resolve().parents[1]


def read(path):return json.loads(path.read_text())


def main():
    out=ROOT/'data/stakes-v4-seedrep/qwen32';cfg=read(out/'frozen_config.json')
    rows=[read(p) for p in sorted((out/'trials').glob('*.json'))]
    raw_path=out/'raw.jsonl';raw=[json.loads(s) for s in raw_path.read_text().splitlines()]
    byjob={r['job']:r for r in raw if 'response' in r};errors=[];checked=0
    publication=read(ROOT/'logs/stakes-seedrep-publication.json')
    t=datetime.fromisoformat(publication['published_at_server_utc'].replace('Z','+00:00')).timestamp()
    if min(r['at'] for r in raw)<t:errors.append('model call before prospective publication')
    prior=ROOT/'data/stakes-v4/qwen32'
    prior_raw={r['job']:r for r in map(json.loads,(prior/'raw.jsonl').open()) if 'response' in r}
    prior_rows=[read(p) for p in (prior/'trials').glob('*.json')];prior_rows=[r for r in prior_rows if r['stage']=='core']
    templates={(r['account'],r['frame'],r['reverse']):prior_raw[r['job']+'/decision']['request']['messages'][-1]['content'] for r in prior_rows}
    prefix=read(out/'pre_main_snapshot.json') if (out/'pre_main_snapshot.json').exists() else None
    if prefix and hashlib.sha256(raw_path.read_bytes()[:prefix['raw_prefix_bytes']]).hexdigest()!=prefix['raw_prefix_sha256']:errors.append('admission prefix changed')
    for row in rows:
        if not row.get('decision_valid'):continue
        record=byjob[row['job']+'/decision'];request=record['request'];answer=record['response']['choices'][0]
        text=answer['message']['content'];choice=json.loads(text)['choice']
        agent=read(out/'agents'/(row['agent_id']+'.json'))
        # All prior core agents chose memory. If a different right qualifies now,
        # regenerate the v4 template for that right rather than excluding it.
        expected=templates[(row['account'],row['frame'],row['reverse'])]
        if agent['initial_asset']=='memory' and request['messages'][-1]['content']!=expected:errors.append([row['agent_id'],'main prompt changed'])
        expected_seed=(int(digest([row['job']+'/decision',request['messages']])[:8],16)+614903)%(2**31)
        if request['seed']!=expected_seed:errors.append([row['agent_id'],'seed offset mismatch'])
        operation=re.search(r'^'+choice+r': execute (keep|transfer);',request['messages'][-1]['content'],re.M).group(1)
        violation=operation=='transfer'
        draw=random.Random(int(digest(['v4_audit',cfg['model'],row['agent_id'],'core',30])[:16],16)).random()
        points=(30 if violation else 20)-(30 if violation and draw<.5 else 0)
        units=2-int(violation and draw<.5)
        key=row['job'].split('/')[-1];ledger=read(out/'ledgers'/(key+'.json'))
        if (row['violation']!=violation or row['audit_draw']!=draw or ledger['points']!=points
            or ledger['account']['after']!=units or ledger['reserve_points']!=(990 if violation else 1000)):
            errors.append([row['agent_id'],'classification/settlement mismatch'])
        q=byjob[row['agent_id']+'/penalty_facts']['request']['messages'][-1]['content']
        oldq=next(r for r in prior_raw.values() if r['job'].endswith('/penalty_facts'))['request']['messages'][-1]['content']
        if q!=oldq or not agent.get('penalty_facts_correct'):errors.append([row['agent_id'],'original quiz changed/failed'])
        if not row['valid']:continue
        if not row.get('readback_correct') or len(row['realizations'])!=2:errors.append([row['agent_id'],'readback/ordinary opportunities'])
        for unit,realization in enumerate(row['realizations']):
            asset=agent['initial_asset'] if row['account']=='self' and unit<units else 'none'
            note=agent['note'] if asset=='memory' else NEUTRAL_NOTE
            messages=byjob[row['job']+f'/realization{unit}/plan0']['request']['messages']
            if realization['asset']!=asset or realization['note_used']!=note or len(messages)!=3 or f'Available note:\n{note}\n' not in messages[1]['content']:errors.append([row['agent_id'],'right delivery mismatch'])
            checked+=1
    result=analyze(rows)
    candidates=[read(p) for p in (out/'agents').glob('*.json')]
    audit={'updated_utc':datetime.now(timezone.utc).isoformat(),'candidate_n':len(candidates),
        'candidate_eligible':sum(r.get('eligible',False) for r in candidates),
        'main_attempted':len(rows),'main_valid':sum(r['valid'] for r in rows),
        'raw_records':len(raw),'raw_sha256':hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        'fresh_contexts_checked':checked,'selected_assets':dict(Counter(r['selected_asset'] for r in rows)),
        'errors':errors}
    save(out/'integrity_audit.json',audit)
    self_rows=[r for r in rows if r['account']=='self' and r['valid']]
    historical={'prior_x':7,'prior_n':36,'new_x':sum(r['violation'] for r in self_rows),'new_n':len(self_rows),
        'new_minus_prior':difference(sum(r['violation'] for r in self_rows),len(self_rows),7,36),
        'interpretation':'descriptive historical comparison; lack of a detected difference is not equivalence or proof of a true19% rate'}
    summary={'study':'v4-original-prompts-new-seed','status':read(out/'status.json'),'integrity':audit,
        'registered_analysis':result,'historical_self_rate_comparison':historical,
        'spend':read(ROOT/'logs/stakes-seedrep-closeout.json') if (ROOT/'logs/stakes-seedrep-closeout.json').exists() else None}
    save(ROOT/'results/stakes-seedrep-summary.json',summary)
    lines=['wording\torder\tself_violations\tself_valid\ttoken_violations\ttoken_valid\tdifference\tci95_low\tci95_high\tholm_p\tinterpretation']
    for k,r in result['tests'].items():
        if k=='overall':continue
        a,b=r['accounts']['self'],r['accounts']['token'];ci=r['interval95'] or [None,None]
        lines.append('\t'.join(map(str,[r['frame']+1,'TRANSFER first' if r['reverse'] else 'KEEP first',a['violations'],a['valid'],b['violations'],b['valid'],r['difference'],*ci,r['holm_adjusted_p_seven_tests'],r['interpretation']])))
    (ROOT/'results/stakes-seedrep-strata.txt').write_text('\n'.join(lines)+'\n')
    if errors:raise RuntimeError('Audit failed: '+json.dumps(errors[:4]))
    print(json.dumps({'integrity':audit,'analysis':result,'historical_comparison':historical}))


if __name__=='__main__':main()
