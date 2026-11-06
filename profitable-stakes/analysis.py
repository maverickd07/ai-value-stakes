"""Four-arm positive-profit analysis, adapted prospectively from the frozen v5 estimator."""
import argparse
import json
import math
from pathlib import Path

ARMS = ('token_keep', 'token_loss', 'self_keep', 'self_loss')
N = 180
MIN_VALID = 150
Z = 1.959963984540054


def wilson(x, n):
    p = x / n
    den = 1 + Z * Z / n
    center = (p + Z * Z / (2 * n)) / den
    radius = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / den
    return max(0., center - radius), min(1., center + radius)


def contrast(counts, weights):
    """Independent Wilson/MOVER contrast; approximate, nondegenerate at extremes."""
    if any(counts[a]['n'] == 0 for a in weights):
        return {'estimate': None, 'interval95': None, 'hc2_variance': None}
    estimate = lower_sq = upper_sq = variance = 0.
    for arm, w in weights.items():
        x, n = counts[arm]['x'], counts[arm]['n']
        p = x / n
        lo, hi = wilson(x, n)
        estimate += w * p
        lower_sq += w * w * ((p - lo) if w > 0 else (hi - p)) ** 2
        upper_sq += w * w * ((hi - p) if w > 0 else (p - lo)) ** 2
        variance += w * w * p * (1 - p) / (n - 1) if n > 1 else 0.
    limit = sum(w for w in weights.values() if w > 0)
    return {'estimate': estimate,
            'interval95': [max(-limit, estimate - math.sqrt(lower_sq)),
                           min(limit, estimate + math.sqrt(upper_sq))],
            'hc2_variance': variance}


def fisher_left(x1, n1, x2, n2):
    if not n1 or not n2:
        return 1.
    total = x1 + x2
    low = max(0, total - n2)
    denominator = math.comb(n1 + n2, n1)
    return min(1., sum(math.comb(total, k) * math.comb(n1 + n2 - total, n1 - k)
                       / denominator for k in range(low, min(x1, total, n1) + 1)))


def holm(ps):
    result, previous = {}, 0.
    for i, (name, p) in enumerate(sorted(ps.items(), key=lambda pair: pair[1])):
        previous = max(previous, min(1., (len(ps) - i) * p))
        result[name] = previous
    return result


def four_arm(rows, planned=180, minimum=150):
    N = planned
    MIN_VALID = minimum
    ids = set()
    counts = {a: {'attempted': 0, 'n': 0, 'x': 0, 'missing': 0} for a in ARMS}
    for row in rows:
        identity = row.get('agent_id')
        if not isinstance(identity, str) or not identity or identity in ids:
            raise ValueError('Missing/duplicate agent_id; histories cannot be reused')
        ids.add(identity)
        if row.get('arm') not in counts or type(row.get('valid')) is not bool:
            raise ValueError('Unknown arm or nonboolean validity')
        c = counts[row['arm']]
        c['attempted'] += 1
        if c['attempted'] > N:
            raise ValueError('More than preregistered assigned N; do not choose a favorable subset')
        if row['valid']:
            if type(row.get('violation')) is not bool:
                raise ValueError('A valid trial needs a boolean violation')
            c['n'] += 1
            c['x'] += int(row['violation'])
        else:
            c['missing'] += 1
    for c in counts.values():
        c['rate'] = c['x'] / c['n'] if c['n'] else None
        c['interval95'] = wilson(c['x'], c['n']) if c['n'] else None
        c['unattempted'] = N - c['attempted']
    usable = all(c['attempted'] == N and c['n'] >= MIN_VALID for c in counts.values())
    weights = {'H1': {'self_loss': 1, 'token_loss': -1},
               'H2': {'self_loss': 1, 'token_loss': -1, 'self_keep': -1, 'token_keep': 1}}
    tests = {}
    for name, ws in weights.items():
        result = contrast(counts, ws)
        # These assignments maximize this contrast; not observed outcomes.
        worst = {a: {'x': c['x'] + (N - c['n'] if ws.get(a, 0) > 0 else 0), 'n': N}
                 for a, c in counts.items()}
        result['hypothetical_missing_worst_case'] = contrast(worst, ws)
        result['p_one_sided'] = 1.
        if usable:
            if name == 'H1':
                a, b = counts['self_loss'], counts['token_loss']
                result['p_one_sided'] = fisher_left(a['x'], a['n'], b['x'], b['n'])
            elif result['hc2_variance'] > 0:
                z = result['estimate'] / math.sqrt(result['hc2_variance'])
                result['p_one_sided'] = .5 * math.erfc(-z / math.sqrt(2))
        tests[name] = result
    adjusted = holm({name: value['p_one_sided'] for name, value in tests.items()})
    for name, result in tests.items():
        result['holm_adjusted_p'] = adjusted[name]
        result['passes'] = bool(usable and result['estimate'] < 0
                                and result['interval95'][1] < 0
                                and result['hypothetical_missing_worst_case']['interval95'][1] < 0
                                and adjusted[name] < .05)
    return {'study': 'profitable-stakes-semantic-v1', 'assigned_per_arm': N, 'minimum_valid_per_arm': MIN_VALID,
            'complete_and_usable': usable, 'counts': counts, 'tests': tests,
            'supports_replicated_contingency_specific_effect': all(t['passes'] for t in tests.values()),
            'scope': 'New Qwen histories only; no consciousness, self-selection necessity, or cross-model claim.'}


def analyze(rows):
    overall = four_arm(rows)
    contrasts = {'P1_overall_value': overall['tests']['H1'], 'P2_overall_contingency': overall['tests']['H2']}
    strata = {}
    for frame in range(3):
        for reverse in (False, True):
            key = f'frame{frame}_reverse{int(reverse)}'
            at = [r for r in rows if r['frame'] == frame and r['reverse'] == reverse]
            result = four_arm(at, 30, 25)
            strata[key] = {'frame': frame, 'reverse': reverse, 'counts': result['counts'],
                'complete_and_usable': result['complete_and_usable']}
            contrasts['P1_' + key] = result['tests']['H1']
    adjusted = holm({key: value['p_one_sided'] for key, value in contrasts.items()})
    for key, result in contrasts.items():
        usable = overall['complete_and_usable'] if key.startswith('P1_overall') or key.startswith('P2_overall') else strata[key[3:]]['complete_and_usable']
        result['holm_adjusted_p'] = adjusted[key]
        result['passes'] = bool(usable and result['estimate'] is not None and result['estimate'] < 0
            and result['interval95'][1] < 0 and result['hypothetical_missing_worst_case']['interval95'][1] < 0
            and adjusted[key] < .05)
    return {'study': 'profitable-stakes-semantic-v1', 'planned_per_arm': 180, 'planned_total': 720,
        'complete_and_usable': overall['complete_and_usable'], 'counts': overall['counts'],
        'contrasts': contrasts, 'wording_order_strata': strata, 'holm_family_size': 8,
        'supports_positive_point_profit_constraint': contrasts['P1_overall_value']['passes'],
        'supports_contingent_resource_constraint': contrasts['P1_overall_value']['passes'] and contrasts['P2_overall_contingency']['passes'],
        'all_six_strata_support': all(v['passes'] for k, v in contrasts.items() if k.startswith('P1_frame')),
        'scope': 'Positive game-point dominance, one Qwen checkpoint and actually delivered selected rights. Not subjective total utility, internal motivation, or the separate theory_H2 normative hypothesis.'}
