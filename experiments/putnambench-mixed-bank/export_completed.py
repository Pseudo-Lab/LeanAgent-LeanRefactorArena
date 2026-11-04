"""Export only finalized, audited local runs. Never calls a model or Lean."""
import argparse
from decimal import Decimal
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())
def write(p, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2)+'\n')

def export(runtime, run, output):
    sys.path[:0] = [str(runtime/'src'), str(runtime/'experiments/putnambench-bank-pilot')]
    transport = importlib.import_module('openai_transport')
    auditor = importlib.import_module('report')
    from lean_agent.evaluator.tokens import proof_body
    policy = importlib.import_module('policy')
    token_spec = importlib.util.spec_from_file_location('arena_tokens', runtime/'experiments/proof-analyze/proof_tokens.py')
    tokenizer = importlib.util.module_from_spec(token_spec); token_spec.loader.exec_module(tokenizer)
    ledger = read(run/'ledger.json')
    rows = []
    for number in range(51,61):
        folder = run/'problems'/f'F{number:03}'
        if not (folder/'summary.json').exists(): continue
        summary = read(folder/'summary.json')
        if not summary.get('all_versions_valid') or summary.get('final') is None: continue
        assert summary['status'] in ('completed','stopped')
        if summary['status']=='stopped': assert summary['stop_reason']=='cost_limit'
        problem = read(folder/'input/problem.json')
        code = folder/'selected.lean'
        assert sha(code)==summary['selected']['sha256']
        policy.validate_declaration(code.read_text(), problem['statement'])
        final = read(folder/'final/result.json')
        compatibility = read(folder/'compatibility'/sha(code)/'result.json')
        assert final['valid'] and compatibility['valid']
        assert set(compatibility['environments'])==set(problem['environments'])
        assert all(e['valid'] for e in compatibility['environments'].values())
        assert tokenizer.proof_length(code.read_text(), problem['statement']) == summary['final']['tokens']
        assert len(summary['final']['raw_samples'])==3
        assert len(summary['baseline']['raw_samples'])==3
        records = [(k,v) for k,v in ledger['attempts'].items() if v['row']==number]
        auditor.audit_portfolio(folder, summary, records)
        cost = Decimal(0); calls=[]
        for attempt, item in records:
            assert cost < Decimal('2.50')
            assert item['status']=='settled'
            step = folder/'steps'/f"{item['step']:04}"
            raw = read(step/'provider-response.json')
            receipt = transport.compute_cost(raw)
            assert receipt==read(step/'cost-receipt.json')
            assert receipt['provider_response_sha256']==item['provider_response_sha256']
            assert Decimal(receipt['cost_usd'])==Decimal(item['cost_usd'])
            cost += Decimal(receipt['cost_usd'])
            calls.append({'attempt_id':attempt,'step':item['step'],'cost_usd':receipt['cost_usd'],
                          'cost_receipt':receipt,'usage':raw['usage'],
                          'request_sha256':item['request_sha256']})
        assert cost==Decimal(summary['cost_usd']) and len(records)==summary['calls']
        # Verify archived compiler source/log bytes for final measurements and compatibility.
        for directory, result in [(folder/'final', final),(folder/'compatibility'/sha(code),compatibility)]:
            for env,value in result['environments'].items():
                for record in value['runs']:
                    assert sha(directory/env/record['source'])==record['source_sha256']
                    assert sha(directory/env/record['log'])==record['log_sha256']
        name=summary['name']; destination=output/'proofs'/f'{name}.lean'
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(code,destination)
        b,f=summary['baseline'],summary['final']; tr=f['tokens']/b['tokens']; hr=f['raw_heartbeats']/b['raw_heartbeats']
        row={'row':number,'name':name,'selected_candidate':f"c{summary['selected']['step']:03}",
             'proof_sha256':sha(code),'proof_file':str(destination.relative_to(output)),
             'baseline':b,'final':f,'token_reduction_pct':100*(1-tr),'hb_reduction_pct':100*(1-hr),
             'compatibility_ratio':1,'versions':sorted(compatibility['environments']),
             'local_score_estimate':100-100/3*(tr+hr),'cost_usd':str(cost),
             'stop_threshold_usd':'2.50','calls':len(records),'stop_reason':summary['stop_reason'],
             'official_evaluation':False,'provider_invoice_verified':False,'finished_at':summary['finished_at']}
        write(output/'evidence'/name/'measurements.json', {'summary':row,
            'tokenizer':final['tokenizer'], 'versions':{k:{'valid':v['valid'],
            'median_raw_heartbeats':v.get('median_raw_heartbeats'),
            'runs':[{'source_sha256':x['source_sha256'],'log_sha256':x['log_sha256'],
                     'returncode':x['returncode'],'measurement':x.get('measurement')} for x in v['runs']]}
            for k,v in compatibility['environments'].items()},
            'source_receipt_sha256':{'baseline':sha(folder/'baseline/result.json'),
                'final':sha(folder/'final/result.json'),'compatibility':sha(folder/'compatibility'/sha(code)/'result.json'),
                'summary':sha(folder/'summary.json')},
            'baseline_policy':'Original-only receipts reused from earlier offline preparation; final primary HB freshly measured three times.'})
        write(output/'evidence'/name/'costs.json',calls)
        rows.append(row)
    write(output/'results.json',{'scope':'final-adaptation','official_evaluation':False,
        'cost_basis':'OpenAI token usage times frozen public list prices; not invoice verified',
        'completed_count':len(rows),'remaining_count':10-len(rows),'rows':rows,
        'finalized_cost_usd':str(sum((Decimal(r['cost_usd']) for r in rows),Decimal(0)))})
    (output/'submission.partial.jsonl').write_text(''.join(json.dumps({'name':r['name'],'proof':(output/r['proof_file']).read_text()},ensure_ascii=False)+'\n' for r in rows))
    print('Audited and exported',len(rows),'finalized problems; no API/Lean calls.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True);parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parent)
    a=parser.parse_args();export(a.runtime.resolve(),a.run.resolve(),a.output.resolve())
