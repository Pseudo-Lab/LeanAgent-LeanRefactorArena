import sys
from pathlib import Path
import unittest
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'final-batch-next'))
from budget_policy import fit_output
import openai_transport as t
MODEL={'id':t.MODEL_ID,'backend':'openai','max_tokens':8192,'reasoning_effort':'high','seed':42}
class TailBudgetTests(unittest.TestCase):
    def body(self):return t.payload([{'role':'system','content':'hello'*10000},{'role':'user','content':'world'*5000}],MODEL)
    def test_unchanged_when_full_request_fits(self):
        body=self.body(); self.assertEqual(fit_output(body,'1',t.request_cost),body)
    def test_reduction_preserves_input_and_exact_bound(self):
        body=self.body(); full=Decimal(t.request_cost(body)['reserved_usd']); remaining=full-Decimal('.04')
        fitted=fit_output(body,remaining,t.request_cost)
        self.assertLess(fitted['max_completion_tokens'],8192)
        self.assertGreaterEqual(fitted['max_completion_tokens'],2048)
        self.assertEqual(fitted['messages'],body['messages'])
        self.assertEqual(body['max_completion_tokens'],8192)
        self.assertLessEqual(Decimal(t.request_cost(fitted)['reserved_usd']),remaining)
        next_body={**fitted,'max_completion_tokens':fitted['max_completion_tokens']+1}
        self.assertGreater(Decimal(t.request_cost(next_body)['reserved_usd']),remaining)
    def test_no_fit_keeps_request_for_normal_stop_guard(self):
        body=self.body();self.assertEqual(fit_output(body,'0.001',t.request_cost),body)
    def test_minimum_is_not_silently_violated(self):
        with self.assertRaises(ValueError):fit_output(self.body(),'.01',t.request_cost,0)

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch
import tempfile
import json
import run_experiment as experiment

@contextmanager
def unlocked(*args, **kwargs):
    yield

class CoordinatorGuardTests(unittest.TestCase):
    def test_strict_cap_rejects_before_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for arm in experiment.ARMS:
                (root/arm).mkdir();(root/arm/'ledger.json').write_text(json.dumps({'attempts':{}}))
            sent=Mock()
            d=SimpleNamespace(make_request=Mock(),dispatch=sent,check_dispatchable=Mock(),verify_frozen=Mock(),
                transport=SimpleNamespace(request_cost=lambda body:{'reserved_usd':'.11'}),
                locked=unlocked,problem_spend=lambda ledger,row:Decimal('2.90'))
            with patch.object(experiment,'verify',return_value={'api_slots':str(root),'minimum_output_tokens':2048}):
                experiment.install_hooks(root,'control',d)
                with self.assertRaisesRegex(ValueError,'Strict all-stage cap'):
                    d.dispatch(root/'control',6,1,{}, {},root/'step')
            sent.assert_not_called()

    def test_other_arm_unknown_charge_blocks_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for arm in experiment.ARMS:
                (root/arm).mkdir();(root/arm/'ledger.json').write_text(json.dumps({'unknown':arm=='adaptive','attempts':{}}))
            def guard(path,ledger):
                if ledger['unknown']:raise ValueError('Unsettled charge globally prevents further API dispatch')
            sent=Mock()
            d=SimpleNamespace(make_request=Mock(),dispatch=sent,check_dispatchable=guard,verify_frozen=Mock(),
                transport=SimpleNamespace(request_cost=lambda body:{'reserved_usd':'.11'}),
                locked=unlocked,problem_spend=lambda ledger,row:Decimal('0'))
            with patch.object(experiment,'verify',return_value={'api_slots':str(root),'minimum_output_tokens':2048}):
                experiment.install_hooks(root,'control',d)
                with self.assertRaisesRegex(ValueError,'Unsettled charge'):
                    d.dispatch(root/'control',6,1,{}, {},root/'step')
            sent.assert_not_called()

if __name__=='__main__':unittest.main()
