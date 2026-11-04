#!/usr/bin/env python3
"""Write a NEW common CLI configuration with a frozen v1/v2 strategy Bank."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from lean_agent import strategy_bank


def configure(config_path, bank_path, output, top_k=3, contextual=False):
    if output.exists():raise ValueError('Use a new output config; existing inputs are never overwritten')
    config=json.loads(config_path.read_text())
    settings={'bank':json.loads(bank_path.read_text()),'top_k':top_k}
    settings['contextual'] = contextual
    strategy_bank.validate_settings(settings)
    if config.get('agent',{}).get('mode')!='actions-v1':raise ValueError('Expected actions-v1')
    for key in ('problem','template','project','prompt'):
        config[key]=str((config_path.parent/config[key]).resolve())
    owners=[(config['agent'],'corpus'),(config['model'],'responses'),
            (config['lean'],'prepared_environment'),(config.get('usage_cost',{}),'prices')]
    for owner,key in owners:
        if key in owner:owner[key]=str((config_path.parent/owner[key]).resolve())
    config['agent']['strategy_bank']=settings
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
    return config


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config',type=Path,required=True)
    ap.add_argument('--bank',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--top-k',type=int,choices=(1,2,3),default=3)
    ap.add_argument('--contextual',action='store_true')
    args=ap.parse_args()
    configure(args.config,args.bank,args.output,args.top_k,args.contextual)
    print('Configured Bank input only; no model or Lean execution.')


if __name__=='__main__':main()
