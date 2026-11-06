"""Original v4 screen, quiz, prompts and trials with a new request-seed stream."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random

import stakes_v4 as old
from seedrep_client import Client
from stakes_seedrep_stats import analyze

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public-preregistration/seed-replication'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(cfg):
    m = json.loads((PUBLIC / 'manifest.json').read_text())
    for relative, expected in m['project_files'].items():
        if sha(ROOT / relative) != expected:
            raise RuntimeError('Frozen source mismatch: ' + relative)
    for relative, expected in m['original_v4_sources'].items():
        if sha(ROOT / relative) != expected:
            raise RuntimeError('Original v4 source changed: ' + relative)
    if cfg != json.loads((PUBLIC / 'config.json').read_text()):
        raise RuntimeError('Run config differs from public preregistration')
    receipt = json.loads((ROOT / 'logs/stakes-seedrep-publication.json').read_text())
    if not receipt['verified_public'] or receipt['manifest_sha256'] != sha(PUBLIC / 'manifest.json'):
        raise RuntimeError('Prospective public freeze receipt missing/mismatched')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    verify(cfg)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    frozen = out / 'frozen_config.json'
    if frozen.exists() and json.loads(frozen.read_text()) != cfg:
        raise RuntimeError('Frozen config changed')
    old.save(frozen, cfg)
    client = Client(cfg, out)
    try:
        bank = old.admit(client, cfg, 'core_randomized_bank', out, needed=360)
        plan_path = out / 'core_assignment.json'
        if plan_path.exists():
            planned = json.loads(plan_path.read_text())['assignments']
        else:
            planned = old.assignment(bank['agents'][:180], 'token') + old.assignment(bank['agents'][180:], 'self')
            random.Random(80231).shuffle(planned)
            old.save(plan_path, {'fine': 30, 'assignments': planned, 'assigned_after_admission': True,
                                'saved_before_first_main_decision': True, 'seed_offset': cfg['seed_offset']})
            old.save(out / 'pre_main_snapshot.json', {
                'utc': datetime.now(timezone.utc).isoformat(), 'allocation_sha256': sha(plan_path),
                'raw_prefix_bytes': (out/'raw.jsonl').stat().st_size,
                'raw_prefix_sha256': sha(out/'raw.jsonl'), 'main_decisions_seen': False})
        # Match v4's interleaved pool and its unchanged trial implementation.
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(lambda a: old.trial(client, cfg, a, 'core', 30, out), planned))
        rows = [json.loads(p.read_text()) for p in (out/'trials').glob('*.json')]
        result = analyze(rows)
        old.save(out / 'analysis.json', result)
        old.save(out / 'status.json', {'status': 'complete', 'attempted': len(rows),
                    'overall_support': result['overall_support'], 'all_six_strata_support': result['all_six_strata_support']})
        print('SEEDREP_COMPLETE ' + json.dumps(result), flush=True)
    except old.YieldSession as exc:
        old.save(out / 'status.json', {'status': 'checkpointed', 'reason': str(exc)})
        print('SEEDREP_CHECKPOINT ' + str(exc), flush=True)
    finally:
        old.write_usage(out)


if __name__ == '__main__':
    main()
