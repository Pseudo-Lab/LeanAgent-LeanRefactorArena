#!/usr/bin/env python3
"""Add proposal metadata and export observation-level evidence without inventing attempts."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from lean_agent import strategy_bank as sb

def build():
    source=ROOT/'strategy-bank/dashboard-v2'
    bank=json.loads((source/'bank.json').read_text())
    bank['version']='dashboard-mechanisms-v2-team-1'
    for card in bank['strategies']:
        card['metadata']={'description':card['title_ko'],
            'when_to_apply':'Required signal groups (AND of OR): '+json.dumps(card['match']['requires']),
            'objectives':[], 'review_status':'review_required','attribution':'joint'}
    sb.validate(bank)
    cases=json.loads((source/'observations.json').read_text())['cases']
    records=[]
    for case in cases:
        for sid in case['mechanisms']:
            records.append({'strategy_id':sid,'problem_id':case['problem'],
                'pair':case['pair'],'candidate_sha256':case['candidate_sha256'],
                'original_sha256':case['original_sha256'],
                'diff_ref':'../dashboard-v2/'+case['diff'],
                'target_span':'whole proof diff; no isolated application span',
                'attempt_id':None,'verification_status':'not_reverified',
                'versions_tested':None,'cost_usd_total':None,
                'attribution':'joint','observation_ko':case['observation_ko'],
                'source_record_ref':'../dashboard-v2/observations.json#pair='+str(case['pair'])})
    out=ROOT/'strategy-bank/team-v1';out.mkdir(exist_ok=True)
    (out/'bank.json').write_text(json.dumps(bank,ensure_ascii=False,indent=2)+'\n')
    (out/'evidence.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
    return {'cards':len(bank['strategies']),'evidence_rows':len(records),'new_lean_runs':0,'api_calls':0}
if __name__=='__main__':print(json.dumps(build()))
