"""Mixed retrieval contracts; runnable with the archived common runtime."""
import copy
import unittest
from lean_agent import strategy_bank as sb


def settings():
    return {'bank': {'schema_version': 1, 'version': 'test', 'scope': 'warmup',
        'strategies': [{'id': 'S1', 'title': 'test', 'match': {}, 'guide': 'test',
        'risks': 'test', 'evidence': [{'problem': 'other', 'candidate_sha256': 'a'*64}]}]},
        'top_k': 1, 'contextual': True, 'search_policy': 'alternating-v1'}


def request(count):
    return {'best': {'tokens': 2, 'raw_heartbeats': 10},
            'baseline': {'tokens': 4, 'raw_heartbeats': 20},
            'exploration': {'candidate_count': count, 'recent_actions': []}}


class MixedTests(unittest.TestCase):
    def test_candidate_sequence_and_tool_calls(self):
        s = settings()
        self.assertEqual([sb.search_mode(s, request(n)) for n in range(1, 6)],
                         ['free', 'guided', 'free', 'guided', 'free'])
        for step in (1, 3, 20):
            r = request(1); r['step'] = step
            self.assertEqual(sb.search_mode(s, r), 'free')

    def test_free_has_no_cards_signals_or_evidence(self):
        value = sb.for_request({'name': 'p', 'reference': 'by rfl'}, settings(), request(1))
        self.assertEqual(value['strategies'], [])
        self.assertEqual(value['strategy_hints'], [])
        self.assertNotIn('context', value)
        self.assertNotIn('matched_signals', value)

    def test_guided_retains_retrieval(self):
        value = sb.for_request({'name': 'p', 'reference': 'by rfl'}, settings(), request(2))
        self.assertEqual(value['search_mode'], 'guided')
        self.assertEqual(value['strategies'][0]['id'], 'S1')

    def test_hidden_has_no_mixed_context(self):
        value = sb.for_request({'name': 'p'}, settings(), {}, hidden=True)
        self.assertEqual(value['status'], 'withheld_hidden_original')
        self.assertNotIn('context', value)
        self.assertNotIn('search_mode', value)

    def test_history_redaction_does_not_mutate_receipts(self):
        original = {'best': {'code': 'by rfl', 'strategy': 'Bank idea'},
                    'exploration': {'recent_actions': [{'action': {
                        'action': 'propose', 'strategy_ids': ['S1'], 'strategy': 'idea'},
                        'outcome': {'status': 'proof_rejected'}}]}}
        before = copy.deepcopy(original)
        result = sb.without_strategy_history(original)
        self.assertEqual(original, before)
        self.assertNotIn('strategy', result['best'])
        self.assertNotIn('strategy_ids', result['exploration']['recent_actions'][0]['action'])
        self.assertEqual(result['best']['code'], 'by rfl')
        self.assertEqual(result['exploration']['recent_actions'][0]['outcome']['status'], 'proof_rejected')

    def test_legacy_output_unchanged(self):
        s = settings(); s.pop('search_policy')
        r = request(1); problem = {'name': 'p', 'reference': 'by rfl'}
        old = sb.for_request(problem, s, r)
        self.assertNotIn('search_mode', old)
        self.assertEqual(old['strategies'][0]['id'], 'S1')

    def test_invalid_policy_and_missing_counter(self):
        s = settings(); s['search_policy'] = 'random'
        with self.assertRaises(ValueError): sb.validate_settings(s)
        with self.assertRaises(ValueError): sb.search_mode(settings(), {})


if __name__ == '__main__': unittest.main()
