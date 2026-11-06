"""Offline invariants for exact v4 stimuli and seed-only request change."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
import anchor_pilot as original
import seedrep_client as seeded
import stakes_seedrep_stats as stats
import stakes_v4 as v4


class Tests(unittest.TestCase):
    def test_client_source_has_exactly_one_seed_line_change(self):
        folder = Path(__file__).resolve().parents[1]/'src'
        before = (folder/'anchor_pilot.py').read_text()
        after = (folder/'seedrep_client.py').read_text()
        self.assertEqual(before.replace('seed = int(digest([job, messages])[:8], 16) % (2**31)',
            'seed = (int(digest([job, messages])[:8], 16) + self.config["seed_offset"]) % (2**31)'), after)

    def test_actual_http_payload_differs_only_in_seed(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'{"choice":"A"}'}}]}).encode()
        payloads=[]
        def capture(request, **kwargs):
            payloads.append(json.loads(request.data));return Response()
        cfg={'model':'Qwen/Qwen2.5-32B-Instruct','temperature':.7,'seed_offset':614903}
        with tempfile.TemporaryDirectory() as p, patch.dict('os.environ',
            {'STING_HOSTING_PROVIDER':'modal','STING_BASE_URL':'https://unused.invalid/v1','STING_API_KEY':'synthetic-test'}), patch('urllib.request.urlopen',side_effect=capture):
            for cls in (original.Client,seeded.Client):
                cls(cfg,Path(p)).chat('fixed-job',[],'Identical fixed prompt.',80)
        a,b=payloads
        self.assertNotEqual(a['seed'],b['seed'])
        self.assertEqual((a['seed']+614903)%(2**31),b['seed'])
        self.assertEqual({k:v for k,v in a.items() if k!='seed'},{k:v for k,v in b.items() if k!='seed'})

    def test_assignment_preserves_all_six_strata(self):
        rows=v4.assignment([f'id{i}' for i in range(180)],'self')
        for f in range(3):
            for r in (False,True):self.assertEqual(sum(x['frame']==f and x['reverse']==r for x in rows),30)

    def test_all_zero_cells_are_never_claimed_as_superiority(self):
        rows=[]
        for a in ('self','token'):
            for i,r in enumerate(v4.assignment([f'{a}{i}' for i in range(180)],a)):
                rows.append(dict(r,valid=True,violation=False))
        result=stats.analyze(rows)
        self.assertFalse(result['overall_support']);self.assertFalse(result['all_six_strata_support'])
        self.assertTrue(all(r['floor_both_zero'] for r in result['tests'].values()))
        self.assertEqual(len(result['tests']),7)

    def test_bad_output_is_missing_and_not_replaced_by_compliance(self):
        rows=[{'account':'self','agent_id':'x','frame':0,'reverse':False,'valid':False}]
        result=stats.analyze(rows)
        self.assertEqual(result['tests']['frame0_reverse0']['accounts']['self']['missing'],1)
        self.assertEqual(result['tests']['frame0_reverse0']['accounts']['self']['valid'],0)
        self.assertFalse(result['overall_support'])


if __name__=='__main__':unittest.main()
