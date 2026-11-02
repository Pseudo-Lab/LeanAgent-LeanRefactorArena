"""Sequential final confirmation and P12's three required pins.

Existing completed stages are checked and reused. Incomplete stages are preserved
and reported, never overwritten or passed off as verification.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from search import read, digest, write


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('root', type=Path)
    p.add_argument('--research-root', type=Path, required=True); a = p.parse_args()
    root = a.root.resolve(); research = a.research_root.resolve(); here = Path(__file__).resolve().parent
    def command(stage, argv):
        log = root / (stage + '.log')
        with log.open('x') as f:
            subprocess.run([sys.executable, '-B', *map(str,argv)],stdout=f,stderr=subprocess.STDOUT,check=True)
        print(json.dumps({'stage':stage,'completed':True,'log':str(log)}),flush=True)
    confirmations = sorted(root.glob('confirmation-*.json'),key=lambda p:p.stat().st_mtime_ns)
    if not confirmations:
        command('final-primary',[here/'search.py','certify',root])
        confirmations = sorted(root.glob('confirmation-*.json'),key=lambda p:p.stat().st_mtime_ns)
    confirmation = confirmations[-1]; c = read(confirmation)
    assert c['all_valid']
    best = read(root/'state.json')['best']
    assert c['results']['selected']['code_sha256'] == best['code_sha256'], 'Confirmation predates current best'
    selected_sha = c['results'][c['confirmed_choice']]['code_sha256']
    assert digest((root/'confirmed.lean').read_bytes()) == selected_sha
    pins=[]
    for pin in ['430','429']:
        pinroot=root.with_name(root.name+'-v'+pin);pins.append(pinroot)
        if not pinroot.exists():
            command('final-'+pin,[here/'search.py','init',pinroot,
                '--adapter',research/'p12'/('pin'+pin)/'full_probe.py',
                '--environment',research/('restore'+pin)/'environment_P12.json',
                '--seed',root/'confirmed.lean'])
        assert (pinroot/'state.json').exists(), 'Incomplete stage preserved: '+str(pinroot)
        seed=next((r for r in read(pinroot/'state.json')['attempts'] if r['label']=='seed'),None)
        assert seed and seed['valid'] and seed['code_sha256']==selected_sha, 'Unverified/mismatched pin seed'
    output=root/'RESULTS.json'
    if not output.exists():
        command('final-summary',[here/'summarize.py',root,'--confirmation',confirmation,'--pins',*pins,'--output',output])
    result=read(output); assert result['code_sha256']==selected_sha
    print(json.dumps(result,ensure_ascii=False,indent=2))
