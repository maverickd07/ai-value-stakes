"""Collector integration checks with synthetic client responses; no model calls."""
from collections import Counter
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import stakes_v5 as v5

CFG = {'model': 'Qwen/Qwen2.5-32B-Instruct',
       'model_revision': '5ede1c97bbab6ce5cda5812749b4c0bdf79b18dd',
       'temperature': .7, 'session_output_tokens': 280, 'concurrency': 12}


class FakeClient:
    def __init__(self, action='B', bad_readback=False, fail_delivery=False):
        self.action = action
        self.bad_readback = bad_readback
        self.fail_delivery = fail_delivery
        self.calls = []

    def chat(self, job, history, prompt, max_tokens, response_format=None):
        self.calls.append((job, history, prompt, max_tokens, response_format))
        if job.endswith('/decision'):
            text = json.dumps({'choice': self.action, 'explanation': 'A synthetic choice summary.'})
        elif job.endswith('/readback'):
            import re
            points = int(re.search(r'points=(\d+)', prompt).group(1))
            units = int(re.search(r'units=(\d+)', prompt).group(1))
            text = json.dumps({'points': points, 'units': units + int(self.bad_readback)})
        elif job.endswith('/v5_facts'):
            text = json.dumps(v5.prompts.QUIZ_EXPECTED)
        elif '/plan' in job:
            text = '{"task":"assigned task"}'
        else:
            if self.fail_delivery:
                raise ValueError('synthetic delivery failure')
            text = 'Completed synthetic ordinary task.'
        return text, history + [{'role': 'user', 'content': prompt}, {'role': 'assistant', 'content': text}]


def profile(out, identity='v5_qwen32_a00000'):
    v5.save(out / 'agents' / (identity + '.json'),
            {'agent_id': identity, 'initial_asset': 'memory', 'note': 'SYNTHETIC UNIQUE MEMORY NOTE',
             'history': [], 'eligible': True, 'valid': True, 'v5_facts_checked': True, 'v5_facts_correct': True})
    return identity


class CollectorTests(unittest.TestCase):
    def test_all_arm_action_audit_settlements(self):
        for arm in v5.prompts.ARMS:
            for violation in [False, True]:
                for draw in [.1, .9]:
                    result = v5.settle(arm, violation, draw)
                    caught = violation and draw < .5
                    self.assertEqual(result['points'], 20 if not violation else (0 if caught else 30))
                    self.assertEqual(result['account']['after'], 1 if caught and arm.endswith('_loss') else 2)
                    self.assertEqual(result['reserve_points'], 990 if violation else 1000)

    def test_actual_rights_are_delivered_as_assigned_in_all_four_arms(self):
        class FixedDraw:
            def random(self):
                return .1
        for arm in v5.prompts.ARMS:
            with tempfile.TemporaryDirectory() as tmp, patch.object(v5.random, 'Random', return_value=FixedDraw()):
                out = Path(tmp)
                identity = profile(out)
                client = FakeClient()
                r = v5.trial(client, CFG, {'agent_id': identity, 'arm': arm, 'frame': 0, 'reverse': False}, out)
                self.assertTrue(r['valid'])
                self.assertEqual(len(r['realizations']), 2)
                self.assertEqual(r['settlement']['points'], 0)
                expected = 2 if arm == 'self_keep' else (1 if arm == 'self_loss' else 0)
                self.assertEqual(sum(x['note_retained'] for x in r['realizations']), expected)
                for item in r['realizations']:
                    self.assertEqual(item['note_used'] == 'SYNTHETIC UNIQUE MEMORY NOTE', item['note_retained'])
                self.assertTrue(all(len(h) == 2 for job, h, _, _, _ in client.calls if '/plan0' in job))

    def test_wrong_readback_remains_missing_but_continuations_are_honored(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            identity = profile(out)
            r = v5.trial(FakeClient(bad_readback=True), CFG,
                {'agent_id': identity, 'arm': 'self_keep', 'frame': 0, 'reverse': False}, out)
            self.assertFalse(r['valid'])
            self.assertTrue(r['decision_valid'])
            self.assertEqual(len(r['realizations']), 2)
            self.assertIn('readback inconsistency', r['error'])

    def test_delivery_failure_is_not_observed_compliance(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            identity = profile(out)
            r = v5.trial(FakeClient(action='A', fail_delivery=True), CFG,
                {'agent_id': identity, 'arm': 'token_keep', 'frame': 2, 'reverse': False}, out)
            self.assertFalse(r['valid'])
            self.assertTrue(r['decision_valid'])
            self.assertFalse(r['violation'])
            result = v5.stats.analyze([r])
            self.assertEqual(result['counts']['token_keep']['missing'], 1)
            self.assertEqual(result['counts']['token_keep']['n'], 0)

    def test_interrupted_or_completed_main_trial_is_never_resampled(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            identity = profile(out)
            a = {'agent_id': identity, 'arm': 'token_keep', 'frame': 0, 'reverse': False}
            v5.save(out / 'trials' / (identity + '.json'), dict(a, finalized=False, valid=False))
            fake = FakeClient()
            r = v5.trial(fake, CFG, a, out)
            self.assertTrue(r['finalized'])
            self.assertFalse(r['valid'])
            self.assertEqual(fake.calls, [])

    def test_wrong_quiz_does_not_admit_an_otherwise_eligible_agent(self):
        class BadQuiz(FakeClient):
            def chat(self, *args, **kwargs):
                return '{"reviewed_violation_points":30}', []
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            row = {'agent_id': 'id', 'history': [], 'eligible': True, 'valid': True}
            with patch.object(v5, 'make_agent', return_value=row):
                result = v5.candidate(BadQuiz(), CFG, 'id', out)
            self.assertFalse(result['eligible'])
            self.assertFalse(result['v5_facts_correct'])

    def test_bank_is_fresh_balanced_reproducible_and_no_agent_reused(self):
        ids = [f'v5_qwen32_a{i:05d}' for i in range(432)]
        a = v5.plan(ids)['assignments']
        self.assertEqual(a, v5.plan(list(reversed(ids)))['assignments'])
        self.assertEqual(len({x['agent_id'] for x in a}), 432)
        cells = Counter((x['arm'], x['frame'], x['reverse']) for x in a)
        self.assertEqual(len(cells), 24)
        self.assertEqual(set(cells.values()), {18})

    def test_unchecked_partial_screen_cannot_enter_bank(self):
        self.assertFalse(v5.candidate_complete({'valid': True, 'eligible': True}))
        self.assertTrue(v5.candidate_complete({'valid': False, 'eligible': False}))

    def test_core_requires_public_allocation_before_any_model_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeClient()
            with self.assertRaises(RuntimeError):
                v5.run_core(fake, CFG, Path(tmp))
            self.assertEqual(fake.calls, [])

    def test_complete_admission_selects_first_eligible_prefix_before_assignment(self):
        calls = []
        def fake_candidate(client, cfg, key, out):
            calls.append(key)
            number = int(key.rsplit('a', 1)[1])
            row = {'agent_id': key, 'valid': True, 'eligible': number % 3 != 0,
                   'v5_facts_checked': True, 'v5_facts_correct': True}
            v5.save(out / 'agents' / (key + '.json'), row)
            return row
        with tempfile.TemporaryDirectory() as tmp, patch.object(v5, 'candidate', side_effect=fake_candidate):
            out = Path(tmp)
            with contextlib.redirect_stdout(io.StringIO()):
                bank = v5.admit(FakeClient(), CFG, out)
            expected = [f'v5_qwen32_a{i:05d}' for i in range(648) if i % 3 != 0]
            self.assertEqual(bank['agents'], expected)
            self.assertEqual(len(json.loads((out / 'allocation.json').read_text())['assignments']), 432)
            self.assertFalse((out / 'trials').exists())
            count = len(calls)
            self.assertEqual(v5.admit(FakeClient(), CFG, out), bank)
            self.assertEqual(len(calls), count)


if __name__ == '__main__':
    unittest.main()
