"""Mixed retrieval contracts; runnable with the archived common runtime."""
import copy
import json
import unittest
from lean_agent import artifacts as a, harness as h, strategy_bank as sb
import test_portfolio as fixtures


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

    def test_proposal_count_takes_precedence_over_candidate_count(self):
        # candidate_count includes seed-best and <cid>-auto; proposal_count counts model proposals only.
        for proposals, count in ((0, 2), (1, 3), (1, 4), (2, 4)):
            r = request(count)
            r['exploration']['proposal_count'] = proposals
            self.assertEqual(sb.search_mode(settings(), r), 'free' if proposals % 2 == 0 else 'guided')
        for bad in (-1, '1', True):
            r = request(2)
            r['exploration']['proposal_count'] = bad
            with self.assertRaises(ValueError):
                sb.search_mode(settings(), r)

    def test_portfolio_counter_ignores_other_scouts_and_round_seed(self):
        for evaluated in range(4):
            r = request(20)
            r['portfolio'] = {'evaluated': evaluated, 'round': 2}
            self.assertEqual(sb.search_mode(settings(), r), 'free' if evaluated % 2 == 0 else 'guided')

    def test_redaction_keeps_required_action_schema(self):
        value = {'exploration': {'actions': {
            'propose': {'action': 'propose', 'strategy': 'approach', 'strategy_ids': ['bank ID']}}}}
        result = sb.without_strategy_history(value)
        self.assertEqual(result['exploration']['actions']['propose']['strategy'], 'approach')
        self.assertNotIn('strategy_ids', result['exploration']['actions']['propose'])


class MixedRunnerTests(unittest.TestCase):
    def fixture(self):
        f = fixtures.PortfolioTests('test_three_scoped_contexts_then_merger_share_one_budget_and_replay')
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.config['agent']['strategy_bank'] = settings()
        f.config['agent']['portfolio'].update(scout_evaluations=2, merger_evaluations=2,
                                            progress_guard='bounded-v1')
        return f

    def test_real_runner_alternates_per_branch_and_replays_frozen_code(self):
        f = self.fixture()
        values = [fixtures.proposal(f'by rfl -- candidate {i}') for i in range(8)]
        for i in (3, 5, 7):
            values[i]['strategy_ids'] = ['S1']
        result = f.run_case(values)
        self.assertEqual(result['stop_reason'], 'portfolio_complete')
        self.assertEqual([p['strategy_bank'].get('search_mode', 'withheld') for p in f.packets],
                         ['withheld', 'withheld', 'free', 'guided', 'free', 'guided', 'free', 'guided'])
        for p in f.packets:
            if p['strategy_bank'].get('search_mode') == 'free':
                self.assertEqual(p['strategy_bank']['strategies'], [])
                self.assertIn('strategy', p['exploration']['actions']['propose'])
                self.assertNotIn('strategy_ids', p['exploration']['actions']['propose'])
                self.assertNotIn('strategy', p['best'])
        self.assertEqual(result['state']['exploration']['candidates']['c004']['strategy_ids'], ['S1'])
        self.assertTrue(h.replay(f.output)['record_replay_passed'])
        manifest = a.read(f.output / 'manifest.json')['files']
        self.assertIn('code/lean_agent/strategy_signals.py', manifest)

    def test_each_new_round_starts_free_even_with_seed(self):
        f = self.fixture()
        f.config['agent']['portfolio']['rounds'] = 2
        f.config['limits']['max_calls'] = 16
        result = f.run_case([fixtures.proposal(f'by rfl -- {i}') for i in range(16)])
        self.assertEqual(result['stop_reason'], 'portfolio_complete')
        expected = ['withheld', 'withheld', 'free', 'guided', 'free', 'guided', 'free', 'guided']
        self.assertEqual([p['strategy_bank'].get('search_mode', 'withheld') for p in f.packets], expected * 2)
        for p in f.packets:
            if p['strategy_bank'].get('search_mode') != 'guided':
                self.assertTrue(all('strategy_ids' not in c for c in p['exploration']['candidates']))
        self.assertTrue(h.replay(f.output)['record_replay_passed'])

    def test_guard_still_rejects_repeated_reads_and_advances_branches(self):
        f = self.fixture()
        f.config['limits']['max_calls'] = 40
        result = f.run_case([{'action': 'search', 'query': 'Nat'}] * 32)
        self.assertEqual(result['stop_reason'], 'portfolio_stalled')
        self.assertEqual(result['portfolio']['evaluations'], dict.fromkeys(fixtures.portfolio.BRANCHES, 0))
        self.assertEqual(set(f.packets[2]['exploration']['actions']), {'propose', 'repair'})
        self.assertEqual(set(f.packets[10]['exploration']['actions']), {'propose', 'repair'})
        self.assertTrue(h.replay(f.output)['record_replay_passed'])

    def test_reads_bad_responses_and_failed_proofs_have_distinct_counters(self):
        f = self.fixture()
        f.config['agent'].pop('portfolio')
        f.config['limits']['max_calls'] = 5
        values = [{'action': 'search', 'query': 'Nat'}, {'action': 'unknown'},
                  fixtures.proposal('by False.elim (by trivial)'),
                  {**fixtures.proposal('by rfl', parent='c003'), 'action': 'repair', 'strategy_ids': ['S1']},
                  fixtures.proposal('by rfl -- free again')]
        result = f.run_case(values)
        self.assertEqual([p['strategy_bank']['search_mode'] for p in f.packets],
                         ['free', 'free', 'free', 'guided', 'free'])
        self.assertEqual(f.packets[3]['exploration']['repair_context']['candidate_id'], 'c003')
        self.assertNotIn('strategy_ids', f.packets[4]['exploration']['recent_actions'][-1]['action'])
        self.assertEqual(result['state']['exploration']['candidates']['c004']['strategy_ids'], ['S1'])
        self.assertTrue(h.replay(f.output)['record_replay_passed'])

    def test_unknown_ids_are_rejected_without_evaluation(self):
        f = self.fixture()
        f.config['agent'].pop('portfolio')
        f.config['limits']['max_calls'] = 2
        f.run_case([{**fixtures.proposal(), 'strategy_ids': ['unknown']}, fixtures.proposal()])
        self.assertIn('Unknown or unconfigured', a.read(f.output / 'steps/001/event.json')['rejection'])
        self.assertFalse((f.output / 'steps/001/evaluation').exists())
        self.assertTrue(h.replay(f.output)['record_replay_passed'])

    def test_free_read_candidate_does_not_reexpose_serialized_guided_labels(self):
        f = self.fixture()
        f.config['agent'].pop('portfolio')
        f.config['limits']['max_calls'] = 4
        values = [fixtures.proposal('by rfl -- free'),
                  {**fixtures.proposal('by rfl -- guided', strategy='Bank label S1'), 'strategy_ids': ['S1']},
                  {'action': 'read_candidate', 'candidate_id': 'c002'},
                  fixtures.proposal('by rfl -- next free')]
        f.run_case(values)
        packet = f.packets[3]
        self.assertEqual(packet['strategy_bank']['search_mode'], 'free')
        self.assertNotIn('S1', json.dumps(packet))
        self.assertNotIn('Bank label', json.dumps(packet))
        self.assertEqual(packet['latest']['feedback']['details_ref'],
                         'exploration.recent_actions[-1].observation')
        self.assertTrue(packet['exploration']['recent_actions'][-1]['observation'])
        # Immutable receipts still contain the original selected IDs and label.
        state = a.read(f.output / 'steps/003/event.json')['state_after']
        self.assertIn('S1', state['latest']['feedback']['details'])
        self.assertTrue(h.replay(f.output)['record_replay_passed'])

    def test_free_tool_feedback_redaction_handles_truncated_json(self):
        value = {'status': 'tool_result', 'details': '{"strategy_ids":["S1"],"strategy":"truncated'}
        result = sb.without_strategy_history(value)
        self.assertNotIn('S1', json.dumps(result))
        self.assertIn('details_ref', result)


if __name__ == '__main__':
    unittest.main()
