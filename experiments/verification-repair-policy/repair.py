"""Bounded recursive repair; global route decisions belong to the Controller."""
from common import ARMS, Stop, canonical, sha
from native import local_closed, patch_site, select_site
from lean_agent import harness
from lean_agent.evaluator.tokens import proof_body

INSTRUCTIONS = (
    'Return exactly one JSON field proof containing a complete Lean by term for this goal. '
    'Preserve its local context and the pinned environment. Do not change the theorem or outer proof. '
    'Implementation-detail locals are compiler metadata, not previously proved lemmas. '
    'Do not use sorry, admit, new axioms, commands, imports or executable metaprograms.'
)


class RepairEngine:
    def __init__(self, runtime, arm, tactics):
        if arm not in ARMS:
            raise ValueError('Unknown experiment condition')
        self.rt, self.arm, self.tactics = runtime, arm, tuple(tactics)
        self.latest_code = None
        self.node_records = []
        self.observations = {}

    def _inspect(self, code):
        report = self.rt.inspect(code)
        self.observations[sha(code)] = report
        return report

    def repair(self, code, route_id):
        rt = self.rt
        self.latest_code, self.route_id = code, route_id
        rt.repair_serial += 1
        self.prefix = f'repair-{rt.repair_serial:03}'
        rt.repair_start = rt.now()
        rt.repair_calls = rt.repair_lean_calls = rt.nodes = 0
        try:
            report = self._inspect(code)
            if report['kind'] != 'proof':
                raise Stop(report['kind'])
            while report['errors']:
                site = select_site(report, code)
                if site is None:
                    raise Stop('extraction_unavailable')
                code, report = self._node(code, site, 1, 'root', [])
                self.latest_code = code
            result = rt.evaluate(code, self.prefix+'-repaired', repair=True)
            if result['valid']:
                return self._result('verified', code=code, evaluation=result)
            return self._result('residual', reason='full_verification_failed', evaluation=result)
        except Stop as exc:
            status = ('limit' if exc.reason.endswith('_limit') else 'cycle' if exc.reason == 'cycle'
                      else 'extraction_unavailable' if exc.reason == 'extraction_unavailable'
                      else 'operational_error' if exc.reason in ('lean_timeout', 'unsettled_receipt')
                      else 'residual')
            return self._result(status, reason=exc.reason)

    def _result(self, status, **values):
        for node in self.node_records:
            if node['status'] == 'open':
                node.update(status='residual', stop_reason=values.get('reason', status))
        digest = sha(self.latest_code)
        observation = self.observations.get(digest)
        next_site = select_site(observation, self.latest_code) if observation and observation['kind'] == 'proof' else None
        remaining = ([] if observation and observation['kind'] == 'proof' and not observation['errors']
                     else next_site['pending_goals'] if next_site else None)
        result = {'status': status, 'route_id': self.route_id, 'nodes': self.node_records,
                  'partial_code': self.latest_code, 'observation_source_sha256': digest if observation else None,
                  'remaining_goals': remaining, 'remaining_goals_scope': 'first_unresolved_native_state',
                  'next_site': next_site, 'diagnostics': observation['errors'] if observation else None, **values}
        self.rt.tape.event('repair_return', result=result)
        return result

    def _node(self, code, site, depth, parent_id, ancestors):
        rt = self.rt
        rt.check_time(repair=True)
        if depth > rt.limits.depth:
            raise Stop('depth_limit')
        if rt.nodes >= rt.limits.nodes:
            raise Stop('node_limit')
        key = sha(canonical({'environment': rt.protocol['environment_sha256'],
                             'target': site['goal']['target'], 'context': site['goal']['local_context']}))
        if key in ancestors:
            rt.tape.event('cycle', parent_id=parent_id, goal_key=key)
            raise Stop('cycle')
        rt.nodes += 1
        node = {'node_id': f'{self.prefix}-node-{rt.nodes:03}', 'parent_id': parent_id, 'depth': depth,
                'goal_key': key, 'site': site, 'worker_calls': 0, 'status': 'open'}
        self.node_records.append(node)
        rt.tape.event('node_created', node=node)

        for tactic in self.tactics:
            proposal, region = patch_site(code, site, 'by ' + tactic)
            if rt.duplicate(proposal):
                continue
            report = self._inspect(proposal)
            solved = local_closed(report, region)
            rt.tape.event('auto_solver', node_id=node['node_id'], tactic=tactic,
                          candidate_sha256=sha(proposal), solved=solved)
            if solved:
                return self._solved(node, proposal, report, 'auto_solver')

        if self.arm != 'recursive-repair-v1':
            node['status'] = 'residual'
            raise Stop('auto_solver_exhausted')

        for call in range(rt.limits.node_calls):
            request = {'node_id': node['node_id'], 'parent_id': parent_id, 'depth': depth,
                       'route_id': self.route_id, 'goal': site['goal'],
                       'environment_sha256': rt.protocol['environment_sha256'],
                       'context': rt.protocol.get('context', {}),
                       'source_sha256': sha(code), 'failed_fragment': code.encode()[site['start']:site['end']].decode(),
                       'instructions': INSTRUCTIONS, 'response_limit_chars': 60000,
                       'remaining_node_calls': rt.limits.node_calls-call}
            raw = rt.dispatch('repair', request)
            node['worker_calls'] += 1
            try:
                statement = 'theorem recursive_repair_fragment : True'
                fragment = harness.parse_proof(raw, {'statement': statement}, 60000)
                proof = proof_body(fragment, statement).strip()
                proposal, region = patch_site(code, site, proof)
            except (ValueError, TypeError) as exc:
                rt.tape.event('worker_rejected', node_id=node['node_id'], reason=str(exc))
                continue
            if rt.duplicate(proposal):
                continue
            report = self._inspect(proposal)
            self.latest_code = proposal
            while not local_closed(report, region):
                child_site = select_site(report, proposal, region)
                if child_site is None:
                    break
                before = len(proposal.encode())
                proposal, report = self._node(proposal, child_site, depth+1, node['node_id'], ancestors+[key])
                region = (region[0], region[1] + len(proposal.encode()) - before)
                self.latest_code = proposal
            if local_closed(report, region):
                return self._solved(node, proposal, report, 'recursive_worker')
            rt.tape.event('worker_unresolved', node_id=node['node_id'], candidate_sha256=sha(proposal))
        node['status'] = 'residual'
        raise Stop('node_call_limit')

    def _solved(self, node, code, report, by):
        node['status'], node['solved_by'] = 'solved', by
        node['result_sha256'] = sha(code)
        self.latest_code = code
        self.rt.tape.event('node_solved', node=node)
        return code, report
