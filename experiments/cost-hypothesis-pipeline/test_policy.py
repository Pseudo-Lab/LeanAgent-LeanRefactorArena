import json
import unittest
from lean_agent import harness as h
import policy


def result(tokens,raw):
    return {'valid':True,'tokens':tokens,'environments':{'fixed':{'valid':True,
        'runs':[{'measurement':{'raw':raw}}]*3}}}


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.problem={'statement':'theorem test : True','reference':'theorem test : True := by trivial\n'}
        self.state=policy.initial(self.problem,result(10,100))

    def card(self,parent='original',family='structure'):
        return dict(parent=parent,family=family,target='whole proof',change='direct constructor',expected_saving='avoid search')

    def advance(self,code,tokens,raw,card=None):
        r=result(tokens,raw)
        return policy.transition(self.state,code,card,r,{'valid':True,'metrics':h.metrics(r)})

    def test_combined_score_can_reject_lower_heartbeat(self):
        s=self.advance('long',20,20)
        self.assertEqual(s['best'],self.state['best'])
        self.assertEqual(len(policy.frontier(s['registry'])),2)

    def test_nonbest_family_parent_survives(self):
        s=self.advance('alternative',20,20,self.card())
        self.assertEqual(s['parents']['structure'],h.digest('alternative'))
        self.assertNotEqual(s['best']['sha256'],s['parents']['structure'])

    def test_invalid_candidate_never_selected(self):
        s=policy.transition(self.state,'bad',self.card(),{'valid':False}, {'valid':False})
        self.assertEqual(s['best'],self.state['best']);self.assertEqual(s['calls'],1)
        self.assertEqual(s['parents'],{})

    def test_duplicate_does_not_profit_from_measurement_noise(self):
        code=self.problem['reference'];s=self.advance(code,10,1)
        self.assertEqual(s['best'],self.state['best'])
        self.assertTrue(s['attempts'][0]['duplicate']);self.assertEqual(s['step'],1)

    def test_distinct_source_kept_even_with_equal_metrics(self):
        s=self.advance('same proof different syntax',10,100)
        self.assertEqual(len(s['registry']),2)

    def test_unknown_parent_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unknown parent'):
            policy.parse({'proof':'by trivial','hypothesis':self.card('invented')},self.problem,'B',self.state)

    def test_control_envelope_unchanged(self):
        code,card=policy.parse({'proof':'by trivial'},self.problem,'A',self.state)
        self.assertIsNone(card);self.assertIn(':= by trivial',code)
        with self.assertRaises(ValueError):
            policy.parse({'proof':'by trivial','hypothesis':self.card()},self.problem,'A',self.state)

    def test_failure_switches_request_stage(self):
        self.state['latest']={'code':'bad','feedback':{'valid':False}}
        p=policy.packet(self.state,self.problem,'prompt','B',6)
        self.assertEqual(p['pipeline']['stage'],'repair_or_abandon_failed_hypothesis')

    def test_control_never_receives_treatment_memory(self):
        p=policy.packet(self.state,self.problem,'prompt','A',6)
        self.assertNotIn('pipeline',p)

    def test_transition_does_not_mutate_input(self):
        before=h.canonical(self.state);self.advance('new',2,10,self.card())
        self.assertEqual(before,h.canonical(self.state))

    def test_request_survives_canonical_json_roundtrip(self):
        # Family insertion order differs from JSON's sorted order. Preserve the
        # actual request, including alternatives list ordering, across processes.
        state=self.state
        for index,family in enumerate(('structure','representation','evidence','sharing')):
            r=result(8-index,90-index*10)
            state=policy.transition(state,f'candidate {index}',self.card(family=family),
                                    r,{'valid':True,'metrics':h.metrics(r)})
            original=policy.packet(state,self.problem,'prompt','B',6)
            restored=policy.packet(json.loads(h.canonical(state)),self.problem,'prompt','B',6)
            self.assertEqual(original,restored)

    def test_nonbest_parent_request_survives_json_roundtrip(self):
        state=self.state
        for index,family in enumerate(('structure','representation','evidence','sharing')):
            r=result(20+index,120+index)
            state=policy.transition(state,f'nonbest {index}',self.card(family=family),
                                    r,{'valid':True,'metrics':h.metrics(r)})
            self.assertEqual(policy.packet(state,self.problem,'prompt','B',6),
                             policy.packet(json.loads(h.canonical(state)),self.problem,'prompt','B',6))


if __name__=='__main__':unittest.main()
