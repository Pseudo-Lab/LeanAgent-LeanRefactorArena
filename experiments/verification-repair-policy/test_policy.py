"""Offline policy invariants and prompt controls. No Lean or network needed."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / 'src'))
from lean_agent.artifacts import sha
import policy
import prompts
import adapter


def observed(kind, code='failed', label='attempt-001'):
    return {'label': label, 'policy_state': kind, 'candidate_sha256': sha(code) if code else None,
            'code': code, 'diagnostic': {'excerpt': 'same diagnostic'}}


class ClassifierTests(unittest.TestCase):
    def test_only_explicit_unsolved_goals_are_incomplete(self):
        prefix = '/run/check.lean:4:2: error: '
        cases = [('unsolved goals\nn : Nat\n⊢ n = n', 'incomplete'),
                 ('unsolved goals\n' + prefix + 'unsolved goals', 'incomplete'),
                 ('unsolved goals\n' + prefix + 'type mismatch', 'proof_error'),
                 ('Tactic `assumption` failed\n⊢ False', 'proof_error'),
                 ('unknown identifier `unsolved goals`', 'proof_error')]
        for text, expected in cases:
            self.assertEqual(policy.classify({'kind': 'proof', 'reason': 'lean_check_rejected', 'excerpt': prefix + text}), expected)

    def test_no_goal_data_or_error_evidence_is_unknown(self):
        for excerpt in ('', 'unsolved goals', 'warning: unsolved goals', 'information: error: unsolved goals'):
            self.assertEqual(policy.classify({'kind': 'proof', 'excerpt': excerpt, 'goals': None}), 'unknown')

    def test_operational_failures_and_axioms_are_not_incomplete(self):
        for kind in policy.FATAL:
            self.assertEqual(policy.classify({'kind': kind, 'excerpt': 'error: unsolved goals'}), kind)
        self.assertEqual(policy.classify({'kind': 'proof', 'reason': 'disallowed_axioms'}), 'proof_error')
        self.assertEqual(policy.classify({'kind': 'response'}), 'response_rejected')
        self.assertEqual(policy.classify({'kind': None, 'reason': 'verified'}), 'valid')


class PolicyTests(unittest.TestCase):
    def state(self, kind):
        state = policy.initial(sha('original'))
        decision = policy.decide(policy.POLICIES[0], state, sha('original'))
        return policy.advance(state, decision, observed(kind))

    def test_only_incomplete_row_differs(self):
        for kind in ['valid', 'proof_error', 'incomplete', 'response_rejected', *sorted(policy.FATAL)]:
            state = self.state(kind)
            a, b = [policy.decide(p, state, sha('best')) for p in policy.POLICIES]
            if kind == 'incomplete':
                self.assertEqual(a['action'], 'repair_current')
                self.assertEqual(a['base_candidate_sha256'], sha('failed'))
                self.assertEqual(b['action'], 'replan_from_best')
                self.assertEqual(b['base_candidate_sha256'], sha('best'))
            else:
                self.assertEqual(a, b)

    def test_budget_precedes_failures_and_repair_limit(self):
        for kind in ['incomplete', 'proof_error', 'timeout', 'valid']:
            state = self.state(kind)
            state['repair_calls_used'] = 2
            for p in policy.POLICIES:
                self.assertEqual(policy.decide(p, state, sha('best'), stop_reason='call_limit')['reason'], 'call_limit')

    def test_generation_is_not_a_repair_and_two_followups_are(self):
        state = self.state('proof_error')
        self.assertEqual(state['repair_calls_used'], 0)
        for used in (1, 2):
            d = policy.decide(policy.POLICIES[0], state, sha('best'))
            self.assertEqual(d['action'], 'repair_current')
            state = policy.advance(state, d, observed('proof_error', f'failed-{used}', f'attempt-00{used+1}'))
            self.assertEqual(state['repair_calls_used'], used)
        d = policy.decide(policy.POLICIES[0], state, sha('best'))
        self.assertEqual((d['action'], d['repair_chain_stop_reason']), ('replan_from_best', 'repair_limit'))
        state = policy.advance(state, d, observed('proof_error', 'fresh', 'attempt-004'))
        self.assertEqual((state['repair_calls_used'], state['repair_chain_id']), (0, 'attempt-004'))

    def test_rejected_repair_counts_then_closes_chain(self):
        state = self.state('proof_error')
        d = policy.decide(policy.POLICIES[0], state, sha('best'))
        state = policy.advance(state, d, observed('response_rejected', None, 'attempt-002'))
        self.assertEqual(state['repair_calls_used'], 1)
        d = policy.decide(policy.POLICIES[0], state, sha('best'))
        self.assertEqual((d['action'], d['repair_chain_stop_reason']), ('optimize_best', 'response_rejected'))

    def test_valid_result_precedes_duplicate_and_repair_cap(self):
        state = self.state('valid')
        state['repair_calls_used'] = 2
        state['latest']['duplicate'] = True
        self.assertEqual(policy.decide(policy.POLICIES[0], state, sha('new-best'))['action'], 'optimize_best')

    def test_duplicate_precedes_repair(self):
        state = self.state('proof_error')
        d = policy.decide(policy.POLICIES[0], state, sha('best'))
        state = policy.advance(state, d, observed('proof_error'))
        for p in policy.POLICIES:
            self.assertEqual(policy.decide(p, state, sha('best'))['reason'], 'duplicate')
        original = policy.initial(sha('original'))
        original = policy.advance(original, {'action': 'optimize_best'}, observed('proof_error', 'original'))
        self.assertTrue(original['latest']['duplicate'])


class PromptTests(unittest.TestCase):
    def test_shared_edits_remove_independent_route_control(self):
        common, diff = prompts.build(HERE.parent / 'prompt-design/p01-p05-reasoning-prompts.v4.en.json')
        for forbidden in ('Test two routes within the first three', 'After two failures', 'When few attempts remain'):
            self.assertNotIn(forbidden, common)
        self.assertIn('control.action', common)
        self.assertIn('Minimize T/T₀ + H/H₀', common)
        self.assertIn('selected base proof byte-identical', common)
        self.assertIn('-The original proof is already a valid starting point.', diff)
        self.assertEqual(common, (HERE/'prompt/common-prompt.txt').read_text())
        self.assertEqual(diff, (HERE/'prompt/common-prompt.diff').read_text())

    def test_first_packet_identical_and_only_control_changes_on_same_failure(self):
        best = {'code': 'best'}
        state = policy.initial(sha('best'))
        packet = {'best': best, 'latest': None}
        first = [adapter.decorate(packet, policy.decide(p, state, sha('best')), state, '/root') for p in policy.POLICIES]
        self.assertEqual(first[0], first[1])
        state = policy.advance(state, policy.decide(policy.POLICIES[0], state, sha('best')), observed('incomplete'))
        values = [adapter.decorate(packet, policy.decide(p, state, sha('best')), state, '/root') for p in policy.POLICIES]
        self.assertNotEqual(values[0]['control'], values[1]['control'])
        for value in values:
            value.pop('control')
        self.assertEqual(values[0], values[1])
        self.assertNotIn('policy_id', str(values))


if __name__ == '__main__':
    unittest.main()
