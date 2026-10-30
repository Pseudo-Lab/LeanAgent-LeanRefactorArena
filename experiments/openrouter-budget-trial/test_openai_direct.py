import copy
from contextlib import redirect_stdout
from decimal import Decimal
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from lean_agent import openai_direct as api, models

spec=importlib.util.spec_from_file_location('direct_trial',Path(__file__).with_name('run.py'))
trial=importlib.util.module_from_spec(spec);spec.loader.exec_module(trial)


def response(status='completed'):
    return {'id':'resp_fixture','model':'gpt-6.1-sol','service_tier':'default','status':status,
        'output':[{'type':'reasoning','summary':[]},{'type':'message','role':'assistant',
            'content':[{'type':'output_text','text':'{"proof":"by trivial"}'}]}],
        'usage':{'input_tokens':1000,'input_tokens_details':{'cached_tokens':200,'cache_write_tokens':300},
                 'output_tokens':500,'output_tokens_details':{'reasoning_tokens':400},'total_tokens':1500}}


class DirectTests(unittest.TestCase):
    def setUp(self):
        self.messages=[{'role':'system','content':'Optimize this Lean proof.'},{'role':'user','content':'theorem p : True := by trivial'}]

    def test_responses_wire_is_text_only_and_capped(self):
        b=api.payload(self.messages)
        self.assertEqual(b['model'],'gpt-6.1-sol')
        self.assertEqual(b['reasoning']['effort'],'high')
        self.assertEqual(b['service_tier'],'default')
        self.assertEqual(b['prompt_cache_options']['ttl'],'30m')
        self.assertFalse(b['store']);self.assertEqual(b['tools'],[])
        self.assertTrue(b['text']['format']['strict'])
        self.assertNotIn('provider',b);self.assertNotIn('max_tokens',b)

    def test_cost_ordinary_cached_writes_output_reasoning_counted_once(self):
        r=api.normalize(response(),api.PRICING);b=models.receipt(r)
        expected=(Decimal(500)*2+Decimal(200)*Decimal('.1')+Decimal(300)*Decimal('2.5')+Decimal(500)*10)/1000000
        self.assertEqual(Decimal(b['cost_usd']),expected)
        self.assertEqual(r['cost_basis'],'usage_estimate')
        self.assertEqual(b['content'],'{"proof":"by trivial"}')
        self.assertEqual(r['openai_response'],response())

    def test_incomplete_is_still_accounted_but_not_accepted(self):
        r=api.normalize(response('incomplete'),api.PRICING)
        self.assertIsNotNone(models.receipt(r)['cost_usd'])
        self.assertIsNone(models.receipt(r)['content'])

    def test_missing_or_inconsistent_usage_is_unknown(self):
        invalid=[]
        for key in ['cached_tokens','cache_write_tokens']:
            r=response();del r['usage']['input_tokens_details'][key];invalid.append(r)
        r=response();r['usage']['input_tokens_details']['cache_write_tokens']=900;invalid.append(r)
        r=response();r['usage']['output_tokens_details']['reasoning_tokens']=501;invalid.append(r)
        r=response();r['usage']['input_tokens']=True;invalid.append(r)
        r=response();r['usage']['total_tokens']=1;invalid.append(r)
        r=response();r['service_tier']='priority';invalid.append(r)
        r=response();r['model']='another-model';invalid.append(r)
        for r in invalid:
            with self.subTest(r=r):self.assertIsNone(models.receipt(api.normalize(r,api.PRICING))['cost_usd'])

    def test_refusal_does_not_return_a_proof(self):
        r=response();r['output'][1]['content']=[{'type':'refusal','refusal':'No proof'}]
        self.assertIsNone(models.receipt(api.normalize(r,api.PRICING))['content'])

    def test_native_snapshot_is_priced(self):
        r=response();r['model']='gpt-6.1-sol-2026-09-29'
        self.assertIsNotNone(models.receipt(api.normalize(r,api.PRICING))['cost_usd'])

    def test_reservation_shrinks_and_stops(self):
        previous=20000
        for remaining in map(Decimal,['1','.2','.12','.08']):
            p=api.plan_request(self.messages,remaining,api.PRICING)
            self.assertIsNotNone(p);body,bound,n=p
            self.assertLessEqual(bound,remaining);self.assertLessEqual(body['max_output_tokens'],previous)
            previous=body['max_output_tokens'];self.assertLess(n,200000)
        self.assertIsNone(api.plan_request(self.messages,Decimal('.01'),api.PRICING))
        messages=copy.deepcopy(self.messages);messages[1]['content']='x'*200000
        with self.assertRaises(ValueError):api.plan_request(messages,Decimal('1'),api.PRICING)

    def test_unknown_price_snapshot_is_rejected_before_network(self):
        prices=dict(api.PRICING);prices['output_per_million']='1'
        with self.assertRaises(ValueError):api.plan_request(self.messages,Decimal('1'),prices)

    def test_literal_key_and_backend_separation(self):
        with tempfile.TemporaryDirectory(dir=os.environ['PROJECT_CACHE_DIR']) as d:
            p=Path(d)/'.env';p.write_text("OPENROUTER_API_KEY=wrong\nOPENAI_API_KEY='literal-$(never-execute)'\n")
            self.assertEqual(api.load_key(p),'literal-$(never-execute)')
            p.write_text('OPENROUTER_API_KEY=wrong\n')
            with self.assertRaises(ValueError):api.load_key(p)

    def test_http_uses_official_endpoint_and_single_request(self):
        stream=MagicMock();stream.__enter__.return_value.read.return_value=json.dumps(response()).encode()
        opener=MagicMock();opener.open.return_value=stream
        with patch.dict(os.environ,{'OPENAI_API_KEY':'synthetic-test-key'}),patch.object(api.request,'build_opener',return_value=opener):
            result=api.query(api.payload(self.messages),api.PRICING)
        self.assertEqual(opener.open.call_count,1)
        req=opener.open.call_args.args[0]
        self.assertEqual(req.full_url,'https://api.openai.com/v1/responses')
        self.assertEqual(req.get_header('Authorization'),'Bearer synthetic-test-key')
        self.assertIsNotNone(models.receipt(result)['cost_usd'])
        self.assertNotIn('synthetic-test-key',json.dumps(result))

    def test_timeout_never_retries_and_has_unknown_charge(self):
        opener=MagicMock();opener.open.side_effect=TimeoutError('synthetic-test-key')
        with patch.dict(os.environ,{'OPENAI_API_KEY':'synthetic-test-key'}),patch.object(api.request,'build_opener',return_value=opener):
            result=api.query(api.payload(self.messages),api.PRICING)
        self.assertEqual(opener.open.call_count,1)
        self.assertIsNone(models.receipt(result)['cost_usd'])
        self.assertNotIn('synthetic-test-key',json.dumps(result))

    def test_mutated_wire_is_refused_before_network(self):
        b=api.payload(self.messages);b['service_tier']='priority'
        with patch.object(api.request,'build_opener',side_effect=AssertionError('no network')):
            with self.assertRaises(ValueError):api.query(b,api.PRICING)

    def test_cli_direct_loop_without_any_network_or_real_lean(self):
        with tempfile.TemporaryDirectory(dir=os.environ['PROJECT_CACHE_DIR']) as d:
            temp=Path(d);source=temp/'packets';(source/'P02').mkdir(parents=True);out=temp/'run'
            packet={'problem':{'statement':'theorem p : True','original':'theorem p : True := by trivial','name':'p'},'context':{},'strategy_prompt':'use original'}
            (source/'P02/agent-input.json').write_text(json.dumps(packet))
            (source/'P02/original.lean').write_text(packet['problem']['original'])
            (source/'P02/environment.json').write_text(json.dumps({'environments':[{'project':d,'command':[sys.executable]}]}))
            def fake_eval(folder,label,*args):
                return {'label':label,'valid':True,'tokens':10 if label=='baseline' else 1,
                        'raw_hb':100000 if label=='baseline' else 50000,'hb_k':100 if label=='baseline' else 50}
            def fake_query(body,prices):
                (out/'STOP').touch()
                return api.normalize(response(),prices)
            with patch.multiple(trial,ROOT=trial.ROOT,SOURCE=trial.SOURCE,CAP=trial.CAP,TOTAL_CAP=trial.TOTAL_CAP,PROBLEMS=trial.PROBLEMS,BACKEND=trial.BACKEND,MODEL=trial.MODEL),patch.object(trial.transport,'http',side_effect=AssertionError('OpenRouter must not be called')),patch.object(trial.models,'query',side_effect=AssertionError('OpenRouter must not be called')),patch.object(api,'query',side_effect=fake_query) as query,patch.object(trial,'evaluate',side_effect=fake_eval),patch.dict(os.environ,{'OPENAI_API_KEY':'synthetic-test-key'}),redirect_stdout(io.StringIO()):
                for args in [['prepare','--output',str(out),'--input-root',str(source),'--problems','P02','--backend','openai','--budget-usd','1','--total-budget-usd','.5'],['check','--output',str(out)],['run','--output',str(out)]]:
                    with patch.object(sys,'argv',['run.py',*args]):trial.main()
            self.assertEqual(query.call_count,1)
            protocol=json.loads((out/'protocol.json').read_text());self.assertEqual(protocol['backend'],'openai')
            self.assertEqual(protocol['total_usd'],'0.5')
            ledger=json.loads((out/'budget.json').read_text());entry=next(iter(ledger['attempts'].values()))
            self.assertEqual(entry['status'],'settled');self.assertEqual(entry['cost_basis'],'usage_estimate')
            summary=json.loads((out/'P02/summary.json').read_text())
            self.assertEqual(summary['stop_reason'],'stop_requested');self.assertEqual(summary['best']['tokens'],1)

    def test_total_budget_blocks_another_problem_before_dispatch(self):
        with tempfile.TemporaryDirectory(dir=os.environ['PROJECT_CACHE_DIR']) as d:
            temp=Path(d);source=temp/'packets';out=temp/'run'
            for pid in ['P01','P02']:
                folder=source/pid;folder.mkdir(parents=True)
                packet={'problem':{'statement':'theorem p : True','original':'theorem p : True := by trivial','name':'p'},'context':{},'strategy_prompt':'use original'}
                (folder/'agent-input.json').write_text(json.dumps(packet))
                (folder/'original.lean').write_text(packet['problem']['original'])
                (folder/'environment.json').write_text(json.dumps({'environments':[{'project':d,'command':[sys.executable]}]}))
            with patch.multiple(trial,ROOT=trial.ROOT,SOURCE=trial.SOURCE,CAP=trial.CAP,TOTAL_CAP=trial.TOTAL_CAP,PROBLEMS=trial.PROBLEMS,BACKEND=trial.BACKEND,MODEL=trial.MODEL),patch.object(trial.transport,'http',side_effect=AssertionError('no network')),patch.object(api,'query',side_effect=AssertionError('total budget exhausted')),patch.object(trial,'evaluate',return_value={'label':'baseline','valid':True,'tokens':10,'raw_hb':100000,'hb_k':100}),patch.dict(os.environ,{'OPENAI_API_KEY':'synthetic-test-key'}),redirect_stdout(io.StringIO()):
                with patch.object(sys,'argv',['run.py','prepare','--output',str(out),'--input-root',str(source),'--problems','P01','P02','--backend','openai','--budget-usd','1','--total-budget-usd','.1']):trial.main()
                ledger=json.loads((out/'budget.json').read_text())
                ledger['attempts']['P01/previous']={'status':'settled','cost_usd':'.09','reserved_usd':'.09'}
                (out/'budget.json').write_text(json.dumps(ledger))
                with patch.object(sys,'argv',['run.py','run','--output',str(out),'--problem','P02']):trial.main()
            s=json.loads((out/'P02/summary.json').read_text())
            self.assertEqual(s['history'],[])
            self.assertEqual(s['stop_reason'],'remaining_budget_below_safe_request_bound')
            self.assertEqual(len(json.loads((out/'budget.json').read_text())['attempts']),1)

if __name__=='__main__':unittest.main()
