import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile
import sys
import io
from contextlib import redirect_stdout
from decimal import Decimal

spec=importlib.util.spec_from_file_location('trial',Path(__file__).with_name('run.py'))
trial=importlib.util.module_from_spec(spec);spec.loader.exec_module(trial)

class BudgetTests(unittest.TestCase):
    def setUp(self):
        d=json.loads(Path(__file__).with_name('fixtures').joinpath('openrouter-endpoints.json').read_text())
        self.e=next(e for e in d['data']['endpoints'] if e['tag']=='openai')
        self.messages=[{'role':'system','content':'Lean proof optimization'},{'role':'user','content':'original proof'}]
    def test_normal_and_reduced_output_reserve_within_cap(self):
        for amount in ['1','.2','.1','.07']:
            remaining=Decimal(amount)
            p=trial.plan_request(self.messages,remaining,self.e)
            self.assertIsNotNone(p)
            body,bound,n=p
            self.assertLessEqual(bound,remaining)
            self.assertEqual(body['provider']['allow_fallbacks'],False)
            self.assertEqual(body['plugins'],[])
            self.assertEqual(body['reasoning']['effort'],'high')
            self.assertGreaterEqual(body['max_tokens'],trial.MIN_OUTPUT)
    def test_refuse_tiny_remainder(self):
        self.assertIsNone(trial.plan_request(self.messages,Decimal('.01'),self.e))
    def test_refuse_high_price(self):
        self.e['pricing']['completion']='0.0001'
        with self.assertRaises(ValueError):trial.plan_request(self.messages,Decimal('1'),self.e)
    def test_refuse_large_input(self):
        self.messages[1]['content']='x'*200000
        with self.assertRaises(ValueError):trial.plan_request(self.messages,Decimal('1'),self.e)
    def test_unsettled_charge_blocks_problem(self):
        with self.assertRaises(ValueError):trial.spent({'attempts':{'P01/a':{'status':'uncertain','cost_usd':None}}},'P01')
    def test_costs_are_decimal_per_problem(self):
        d={'attempts':{'P01/a':{'status':'settled','cost_usd':'.1'},'P01/b':{'status':'settled','cost_usd':'.2'},'P02/a':{'status':'settled','cost_usd':'.9'}}}
        self.assertEqual(trial.spent(d,'P01'),Decimal('.3'))
    def test_team_cli_prepare_check_and_stop_are_offline(self):
        import os
        with tempfile.TemporaryDirectory(dir=os.environ['PROJECT_CACHE_DIR']) as directory:
            temp=Path(directory);source=temp/'packets';(source/'P02').mkdir(parents=True)
            (source/'P02/agent-input.json').write_text(json.dumps({'problem':{'statement':'theorem p : True','original':'theorem p : True := by trivial','name':'p'},'context':{},'strategy_prompt':'reason about the original'}))
            (source/'P02/original.lean').write_text('theorem p : True := by trivial')
            (source/'P02/environment.json').write_text(json.dumps({'environments':[{'project':directory,'command':[sys.executable],'template':'not used by offline check'}]}))
            output=temp/'run'
            with patch.multiple(trial,ROOT=trial.ROOT,SOURCE=trial.SOURCE,CAP=trial.CAP,TOTAL_CAP=trial.TOTAL_CAP,PROBLEMS=trial.PROBLEMS,BACKEND=trial.BACKEND,MODEL=trial.MODEL),patch.object(trial.models,'query',side_effect=AssertionError('No paid call permitted')),patch.object(trial.transport,'http',side_effect=AssertionError('No network permitted')),redirect_stdout(io.StringIO()):
                for args in [
                    ['prepare','--output',str(output),'--input-root',str(source),'--problems','P02','--budget-usd','.25'],
                    ['check','--output',str(output)],['stop','--output',str(output)],['run','--output',str(output)]]:
                    with patch.object(sys,'argv',['run.py',*args]):trial.main()
            protocol=json.loads((output/'protocol.json').read_text())
            self.assertEqual(protocol['order'],['P02'])
            self.assertEqual(protocol['prompt_language'],'en')
            self.assertTrue((output/'prompt-design.json').is_file())
            instructions=json.loads((output/'P02/input.json').read_text())['instructions']
            self.assertNotRegex(instructions,r'[가-힣]')
            self.assertEqual(Decimal(protocol['total_usd']),Decimal('.25'))
            self.assertFalse((output/'P01').exists())
            self.assertEqual(json.loads((output/'budget.json').read_text())['attempts'],{})

    def test_missing_input_does_not_create_output(self):
        import os
        with tempfile.TemporaryDirectory(dir=os.environ['PROJECT_CACHE_DIR']) as directory:
            root=Path(directory);out=root/'out'
            with patch.multiple(trial,ROOT=out,SOURCE=root/'missing',PROBLEMS=['P03']):
                with self.assertRaisesRegex(FileNotFoundError,'--input-root must contain existing'):
                    trial.prepare()
            self.assertFalse(out.exists())

    def test_prepare_recovers_empty_dirs_but_never_overwrites_files(self):
        import os
        with tempfile.TemporaryDirectory(dir=os.environ['PROJECT_CACHE_DIR']) as directory:
            root=Path(directory);src=root/'source/P03';src.mkdir(parents=True);out=root/'out'
            original='theorem p : True := by trivial'
            packet={'problem':{'original':original,'statement':'theorem p : True','name':'p'},'context':{},'strategy_prompt':'reason about original'}
            (src/'agent-input.json').write_text(json.dumps(packet))
            (src/'original.lean').write_text(original)
            (src/'environment.json').write_text(json.dumps({'environments':[{'project':directory,'command':[sys.executable]}]}))
            (out/'P03').mkdir(parents=True)
            with patch.multiple(trial,ROOT=out,SOURCE=src.parent,PROBLEMS=['P03']):
                trial.prepare()
                before=(out/'P03/input.json').read_bytes()
                with self.assertRaisesRegex(ValueError,'already prepared'):trial.prepare()
                self.assertEqual((out/'P03/input.json').read_bytes(),before)
            occupied=root/'occupied';occupied.mkdir();(occupied/'notes.txt').write_text('keep')
            with patch.multiple(trial,ROOT=occupied,SOURCE=src.parent,PROBLEMS=['P03']):
                with self.assertRaisesRegex(ValueError,'Output contains files'):trial.prepare()
                self.assertEqual((occupied/'notes.txt').read_text(),'keep')

    def test_every_active_case_and_execution_instruction_is_english(self):
        draft=json.loads(trial.PROMPT_PATH.read_text())
        self.assertEqual(draft['language'],'en')
        self.assertEqual(set(draft['case_prompts']),{'P01','P02','P03','P04','P05'})
        for pid in draft['scope']:
            text=trial.build_instructions(draft,pid,Decimal('.25'))
            self.assertNotRegex(text,r'[가-힣]')
            self.assertIn('at most $0.25 per problem',text)
            self.assertIn('Return exactly one complete candidate as JSON',text)
            self.assertIn('must be in English',text)

if __name__=='__main__':unittest.main()
