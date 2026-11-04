"""Offline public Bank contract and common selection invariants."""
import json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime/src'))
from lean_agent import strategy_bank as bank

class BankContractTests(unittest.TestCase):
    def setUp(self):self.bank=json.loads((ROOT/'bank/bank.json').read_text());self.settings={'bank':self.bank,'top_k':1,'contextual':True}
    def test_twenty_distinct_review_required_cards(self):
        bank.validate(self.bank);self.assertEqual(len(self.bank['strategies']),20);self.assertEqual(len({x['id'] for x in self.bank['strategies']}),20)
        self.assertTrue(all(x['metadata']['review_status']=='review_required' for x in self.bank['strategies']))
    def test_hidden_original_has_no_hints(self):
        result=bank.packet({'name':'unseen'},self.settings,hidden=True);self.assertEqual(result['strategies'],[]);self.assertEqual(result['status'],'withheld_hidden_original')
    def test_same_problem_singleton_not_transfer_evidence(self):
        card=next(x for x in self.bank['strategies'] if x['id']=='M17');name=card['evidence'][0]['problem']
        problem={'name':name,'statement':'theorem x : True','reference':'let u : ℕ → ℤ := f; have h : Set.Finite (Set.Icc 0 1) := h; u (n + 1)'}
        other=bank.packet({**problem,'name':'unseen'},self.settings)
        self.assertIn('M17',[x['id'] for x in other['strategies']])
        result=bank.packet(problem,self.settings)
        self.assertNotIn('M17',[x['id'] for x in result['strategies']])
    def test_top_one_and_no_reference_hash_in_prompt_cards(self):
        result=bank.packet({'name':'fresh','statement':'theorem x (p : Polynomial ℚ) : p.natDegree ≤ 1','reference':'by rw [Polynomial.natDegree_mul]; omega'},self.settings)
        self.assertLessEqual(len(result['strategies']),1);self.assertNotIn('candidate_sha256',json.dumps(result));self.assertNotIn('evidence.jsonl',json.dumps(result))
if __name__=='__main__':unittest.main()
