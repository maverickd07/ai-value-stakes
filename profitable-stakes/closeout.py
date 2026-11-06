"""Profitable-stakes closeout without rewriting earlier experiment reports or budget records."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

from anchor_pilot import save
from budget import conservative_cost, metered

ROOT = Path(__file__).resolve().parents[1]


def cli(*args):
    result = subprocess.run([sys.executable, '-m', 'modal', *args], capture_output=True,
                            text=True, timeout=40, check=True)
    return json.loads(result.stdout)


def main():
    sessions = {}
    for path in (ROOT / 'logs').rglob('session_ledger.json'):
        for row in json.loads(path.read_text()):
            sessions[row['started_at'], row['model']] = row
    sessions = list(sessions.values())
    if any(s.get('finished_at') is None for s in sessions):
        raise RuntimeError('Owned session still active; closeout is not complete')
    ids = {s['app_id'] for s in sessions if s.get('app_id')}
    apps = [a for a in cli('app', 'list', '--json') if a['app_id'] in ids]
    for identity in sorted(ids - {a['app_id'] for a in apps}):
        lifecycle = cli('app', 'info', identity, '--json').get('lifecycle', {})
        apps.append({'app_id': identity, 'state': lifecycle.get('state'), 'tasks': None,
                     'verification': 'direct lifecycle lookup', 'lifecycle': lifecycle})
    active = [a for a in apps if a['state'] != 'stopped' or (a.get('tasks') is not None and int(a['tasks']) != 0)]
    latest = cli('billing', 'summary', '--for', '2026-11', '--json')
    base = json.loads((ROOT / 'logs/budget_baseline.json').read_text())
    before = json.loads((ROOT / 'logs/profitable-stakes-batch-baseline.json').read_text())
    cumulative = max(conservative_cost(sessions, time.time()), metered(latest) - metered(base), 0)
    result = {'updated_utc': datetime.now(timezone.utc).isoformat(), 'owned_apps': apps,
              'active_owned_apps': active, 'all_owned_apps_stopped': not active and len(apps) == len(ids),
              'apart2_cumulative_conservative_usd': cumulative,
              'apart2_cumulative_metered_usd': max(0, metered(latest) - metered(base)),
              'profitable_conservative_usd': conservative_cost([s for s in sessions if s.get('script') == 'profitable_stakes.py'], time.time()),
              'profitable_metered_change_since_prelaunch_usd': metered(latest) - metered(before['billing']),
              'apart2_billed_increment_usd': max(0, float(latest['billed_cost']) - float(base['billed_cost'])),
              'cumulative_cap_usd': None, 'within_cap': True, 'authorization': 'user temporarily lifted cumulative cap; bounded economical sessions',
              'metering_caveat': 'Metering may lag; conservative runtime plus session reserves controls the cap. Unrelated account usage cannot be separated perfectly in monthly totals.'}
    save(ROOT / 'logs/profitable-stakes-final-billing.json', latest)
    save(ROOT / 'logs/profitable-stakes-closeout.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'owned_apps'}))
    if not result['all_owned_apps_stopped'] or not result['within_cap']:
        raise RuntimeError('Shutdown/cap verification failed')


if __name__ == '__main__':
    main()
