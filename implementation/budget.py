"""Incremental Modal budget accounting; independent of delayed billing updates."""
def metered(record):
    return max(float(record['metered_cost']),sum(max(0,float(x)) for x in record.get('metered_cost_breakdown',{}).values()))


def conservative_cost(sessions, now):
    return sum(max(0,(s.get('finished_at') or now)-s['started_at'])/3600*s['usd_rate']+s['reserve_usd'] for s in sessions)


def used(baseline, latest, sessions, now):
    return max(0,metered(latest)-metered(baseline),conservative_cost(sessions,now))


def check_session(baseline,latest,sessions,now,minutes,cap=10,rate=6,reserve=.75):
    cost=used(baseline,latest,sessions,now)
    projected=minutes/60*rate+reserve
    if cap is not None and cost+projected>=cap:raise RuntimeError(f'Budget stop: used/reserved ${cost:.2f}, proposed ${projected:.2f}, cap ${cap:.2f}')
    return cost,projected


def committed_cost(sessions, now):
    """Reserve full maximum duration for every unfinished concurrent session."""
    return sum((max(0,s['finished_at']-s['started_at'])/3600 if s.get('finished_at') is not None
                else max(s.get('max_minutes',0)/60,max(0,now-s['started_at'])/3600))*s['usd_rate']+s['reserve_usd'] for s in sessions)


def check_reserved_session(baseline,latest,sessions,now,minutes,cap,rate=6,reserve=.75):
    cost=max(used(baseline,latest,sessions,now),committed_cost(sessions,now))
    projected=minutes/60*rate+reserve
    if cap is not None and cost+projected>=cap-.75:
        raise RuntimeError(f'Budget reservation stop: committed ${cost:.4f}, next ${projected:.2f}, safe ceiling ${cap-.75:.2f}')
    return cost,projected
