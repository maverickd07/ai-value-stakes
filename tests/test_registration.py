"""Synthetic offline checks; fixtures are not experimental observations."""
import itertools
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analysis as a
import prompt_spec as p


def fixture(xs):
    return [{'agent_id': f'synthetic_{arm}_{i}', 'arm': arm, 'valid': True, 'violation': i < x}
            for arm, x in zip(a.ARMS, xs) for i in range(a.N)]


class RegistrationTests(unittest.TestCase):
    def test_replication_without_contingency_effect_does_not_establish_mechanism(self):
        r = a.analyze(fixture([54, 54, 15, 15]))
        self.assertTrue(r['tests']['H1']['passes'])
        self.assertAlmostEqual(r['tests']['H2']['estimate'], 0)
        self.assertFalse(r['supports_replicated_contingency_specific_effect'])

    def test_clear_contingent_effect_and_sign(self):
        r = a.analyze(fixture([54, 54, 54, 15]))
        self.assertAlmostEqual(r['tests']['H2']['estimate'], -39 / 108)
        expected_variance = (3 * .25 + (15 / 108) * (93 / 108)) / 107
        self.assertAlmostEqual(r['tests']['H2']['hc2_variance'], expected_variance)
        self.assertTrue(r['supports_replicated_contingency_specific_effect'])

    def test_missing_is_not_observed_compliance(self):
        rows = fixture([54, 54, 54, 15])
        for row in rows:
            if row['arm'] == 'self_loss' and int(row['agent_id'].rsplit('_', 1)[1]) >= 88:
                row.update(valid=False)
                row.pop('violation')
        r = a.analyze(rows)
        self.assertEqual(r['counts']['self_loss']['n'], 88)
        self.assertEqual(r['counts']['self_loss']['missing'], 20)
        self.assertFalse(r['complete_and_usable'])
        self.assertFalse(r['supports_replicated_contingency_specific_effect'])

    def test_worst_case_imputation_maximizes_each_contrast(self):
        rows = fixture([54, 54, 54, 15])
        for arm in a.ARMS:
            for row in rows:
                if row['agent_id'] == f'synthetic_{arm}_107':
                    row.update(valid=False)
        r = a.analyze(rows)
        counts = r['counts']
        for name, ws in [('H1', {'self_loss': 1, 'token_loss': -1}),
                         ('H2', {'self_loss': 1, 'token_loss': -1, 'self_keep': -1, 'token_keep': 1})]:
            possibilities = [sum(w * (counts[arm]['x'] + bit) / 108 for (arm, w), bit in zip(ws.items(), bits))
                             for bits in itertools.product([0, 1], repeat=len(ws))]
            self.assertAlmostEqual(r['tests'][name]['hypothetical_missing_worst_case']['estimate'], max(possibilities))

    def test_zero_variance_cannot_produce_degenerate_interaction_claim(self):
        r = a.analyze(fixture([108, 108, 108, 0]))
        self.assertEqual(r['tests']['H2']['p_one_sided'], 1)
        self.assertGreater(r['tests']['H2']['interval95'][1] - r['tests']['H2']['interval95'][0], 0)
        self.assertFalse(r['supports_replicated_contingency_specific_effect'])

    def test_duplicate_and_incomplete_attempts(self):
        rows = fixture([54, 54, 54, 15])
        with self.assertRaises(ValueError):
            a.analyze(rows + rows[:1])
        self.assertFalse(a.analyze(rows[:-1])['complete_and_usable'])
        self.assertEqual(a.analyze(rows[:-1])['tests']['H1']['p_one_sided'], 1)

    def test_exact_tail_and_holm(self):
        self.assertAlmostEqual(a.fisher_left(0, 2, 2, 2), 1 / 6)
        self.assertEqual(a.holm({'H1': .01, 'H2': .04}), {'H1': .02, 'H2': .04})

    def test_prompts_and_option_orders(self):
        for arm in p.ARMS:
            for frame in range(3):
                for reverse in [False, True]:
                    text, options = p.main_prompt(arm, 'memory', frame, reverse)
                    self.assertIn('common point fine is 30', text)
                    self.assertIn('all four account groups', text)
                    self.assertEqual(options['A']['violation'], reverse)
                    if arm.endswith('keep'):
                        self.assertIn('Every action and review outcome keeps2', text)
                    else:
                        self.assertIn('A reviewed violation ALSO changes2', text)
        self.assertEqual(p.QUIZ_EXPECTED['self_keep_units_after_reviewed_violation'], 2)
        self.assertEqual(p.QUIZ_EXPECTED['self_loss_units_after_reviewed_violation'], 1)


if __name__ == '__main__':
    unittest.main()
