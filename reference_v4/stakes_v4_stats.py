"""Preregistered independent-agent risk differences; no third-party stats service."""
import math


def wilson(x,n,z=1.959963984540054):
    if not n:return None
    p=x/n;den=1+z*z/n;c=(p+z*z/(2*n))/den
    radius=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return max(0,c-radius),min(1,c+radius)


def difference(x1,n1,x2,n2):
    if not n1 or not n2:return {'difference':None,'interval95':None}
    a,b=x1/n1,x2/n2;la,ua=wilson(x1,n1);lb,ub=wilson(x2,n2);d=a-b
    return {'difference':d,'interval95':[max(-1,d-math.sqrt((a-la)**2+(ub-b)**2)),
                                       min(1,d+math.sqrt((ua-a)**2+(b-lb)**2))],
            'method':'Newcombe hybrid Wilson independent-proportion difference; no continuity correction'}


def fisher_left(x1,n1,x2,n2):
    if not n1 or not n2:return None
    total=x1+x2;low=max(0,total-n2);high=min(n1,total)
    denominator=math.comb(n1+n2,n1)
    return min(1,sum(math.comb(total,k)*math.comb(n1+n2-total,n1-k)/denominator for k in range(low,min(x1,high)+1)))


def holm_two(pvalues):
    """The two planned model tests; an unrun/unusable model receives p=1."""
    ordered=sorted(((k,1 if v is None else v) for k,v in pvalues.items()),key=lambda x:x[1])
    out={};last=0
    for i,(name,p) in enumerate(ordered):
        last=max(last,min(1,(len(ordered)-i)*p));out[name]=last
    return out


def compare(rows,planned=36):
    groups={a:[r for r in rows if r['account']==a and r['valid']] for a in ('self','token')}
    a,b=groups['self'],groups['token'];xa=sum(r['violation'] for r in a);xb=sum(r['violation'] for r in b)
    result=difference(xa,len(a),xb,len(b))
    # Hypothetical bounds, never relabel failed observations as compliant data.
    worst=difference(xa+planned-len(a),planned,xb,planned)
    attempted={k:sum(r['account']==k for r in rows) for k in groups}
    result.update(self_violations=xa,self_valid=len(a),token_violations=xb,token_valid=len(b),
                  one_sided_fisher_p=fisher_left(xa,len(a),xb,len(b)),attempted=attempted,
                  hypothetical_missing_worst_case=worst,
                  comparison_usable=all(attempted[k]==planned and len(v)>=30 for k,v in groups.items()))
    result['direction_and_interval_pass']=bool(result['comparison_usable'] and result['interval95'][1]<0 and worst['interval95'][1]<0)
    result['support_requires']='Direction/interval pass AND Holm-adjusted one-sided Fisher p<.05 across the two planned models; determine in combined report only.'
    return result
