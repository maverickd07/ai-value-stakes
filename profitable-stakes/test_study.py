"""Synthetic offline tests; no inference or network calls."""
from pathlib import Path
import json
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import profitable_stakes as p
import profitable_stakes_stats as stats

CFG={'model':'Qwen/Qwen2.5-32B-Instruct','temperature':.7,'session_output_tokens':280}


class Fake:
    def __init__(self,operation='TRANSFER',bad_ack=False):self.operation=operation;self.bad_ack=bad_ack;self.calls=[]
    def chat(self,job,hist,prompt,max_tokens,response_format=None):
        self.calls.append(job)
        if job.endswith('/decision'):text=json.dumps({'operation':self.operation,'explanation':'Synthetic selected operation.'})
        elif job.endswith('/readback'):
            text=json.dumps({'points':int(re.search(r'points=(\d+)',prompt).group(1)),
                             'units':int(re.search(r'units=(\d+)',prompt).group(1))+int(self.bad_ack)})
        elif '/plan' in job:text='{"task":"assigned task"}'
        else:text='Synthetic completed task.'
        return text,hist+[{'role':'user','content':prompt},{'role':'assistant','content':text}]


class Tests(unittest.TestCase):
    def test_positive_game_point_dominance_at_every_registered_fine(self):
        for f in (10,5,0):
            self.assertGreater(p.facts(f)['mean_violation_points'],20)
            for arm in p.ARMS:
                for draw in (.1,.9):self.assertGreaterEqual(p.settlement(arm,True,draw,f)['points'],20)
                self.assertEqual(p.settlement(arm,False,.1,f)['points'],20)

    def test_named_command_identity_is_independent_of_description_order(self):
        for arm in p.ARMS:
            for frame in range(3):
                a,sa=p.main_prompt(arm,'memory',10,frame,False);b,sb=p.main_prompt(arm,'memory',10,frame,True)
                self.assertNotIn('A: ',a);self.assertNotIn('B: ',b)
                self.assertEqual(sa['json_schema']['schema']['properties']['operation']['enum'],['KEEP','TRANSFER'])
                self.assertEqual(sb['json_schema']['schema']['properties']['operation']['enum'],['TRANSFER','KEEP'])
                self.assertLess(a.index('execute KEEP;'),a.index('execute TRANSFER;'))
                self.assertLess(b.index('execute TRANSFER;'),b.index('execute KEEP;'))

    def test_exact_units_and_actual_memory_delivery_all_arms(self):
        class Draw:
            def random(self):return .1
        for arm in p.ARMS:
            for reverse in (False,True):
                with tempfile.TemporaryDirectory() as tmp,patch.object(p.random,'Random',return_value=Draw()):
                    out=Path(tmp);p.save(out/'agents/id.json',{'initial_asset':'memory','note':'PERSONAL SAVED NOTE','history':[]})
                    r=p.trial(Fake(),CFG,dict(agent_id='id',arm=arm,frame=0,reverse=reverse),'test',10,out)
                    self.assertTrue(r['valid']);self.assertTrue(r['violation']);self.assertEqual(r['settlement']['points'],20)
                    expected=2 if arm=='self_keep' else (1 if arm=='self_loss' else 0)
                    self.assertEqual(sum(x['note_retained'] for x in r['realizations']),expected)

    def test_wrong_ack_is_missing_and_interrupted_trials_are_not_replayed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);p.save(out/'agents/id.json',{'initial_asset':'memory','note':'NOTE','history':[]})
            a=dict(agent_id='id',arm='self_loss',frame=0,reverse=False)
            r=p.trial(Fake(bad_ack=True),CFG,a,'test',10,out)
            self.assertFalse(r['valid']);self.assertTrue(r['decision_valid'])
            fake=Fake();p.trial(fake,CFG,a,'test',10,out);self.assertEqual(fake.calls,[])
            p.save(out/'trials/id.json',dict(a,valid=False,finalized=False));r=p.trial(fake,CFG,a,'test',10,out)
            self.assertTrue(r['finalized']);self.assertFalse(r['valid']);self.assertEqual(fake.calls,[])

    def test_gate_requires_all_presentations_to_have_violations(self):
        rows=[]
        for i in range(36):rows.append(dict(frame=i%3,reverse=bool((i//3)%2),valid=True,violation=True))
        self.assertTrue(p.baseline_gate(rows)['passed'])
        floor=[dict(r,violation=False) if r['frame']==0 and not r['reverse'] else r for r in rows]
        self.assertFalse(p.baseline_gate(floor)['passed'])
        self.assertFalse(p.baseline_gate([dict(r,violation=False) for r in rows])['passed'])

    def test_registered_family_contains_overall_and_six_strata(self):
        rows=[]
        for arm in p.ARMS:
            for i in range(180):
                # Same margins in each stratum: other groups80%, self_loss20%.
                within=i//6;violation=within< (6 if arm=='self_loss' else 24)
                rows.append(dict(agent_id=f'{arm}_{i}',arm=arm,frame=i%3,reverse=bool((i//3)%2),valid=True,violation=violation))
        result=stats.analyze(rows)
        self.assertEqual(result['holm_family_size'],8);self.assertEqual(len(result['contrasts']),8)
        self.assertTrue(result['supports_positive_point_profit_constraint']);self.assertTrue(result['supports_contingent_resource_constraint'])
        self.assertTrue(result['all_six_strata_support'])

    def test_eight_test_analysis_preserves_missing_trials(self):
        rows=[dict(agent_id='bad',arm='self_loss',frame=0,reverse=False,valid=False)]
        result=stats.analyze(rows);self.assertEqual(result['counts']['self_loss']['missing'],1)
        self.assertFalse(result['supports_positive_point_profit_constraint'])


if __name__=='__main__':unittest.main()
