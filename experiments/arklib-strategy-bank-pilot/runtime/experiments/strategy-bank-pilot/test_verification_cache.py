import importlib.util,json,tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
spec=importlib.util.spec_from_file_location('pilot',Path(__file__).with_name('run.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.env={'id':'v','template':'context','command':['lean']};self.problem={'name':'target','statement':'stmt'}
        self.mod=SimpleNamespace(proof_tokens=lambda c,s:1,ALLOWED_AXIOMS={'propext'},render=lambda t,c,n,nonce:t+'\n'+(('#refactor_eval "'+nonce+'"\n') if nonce else '')+c)
        self.directory=self.root/'v';folder=self.directory/'v';folder.mkdir(parents=True)
        self.result={'valid':True,'tokens':1,'environments':{'v':{'valid':True,'error':None,'runs':[]}},'error':None}
        for i in range(4):
            nonce=('%032x'%i) if i else None;label='check' if not i else 'measure-'+str(i)
            source=folder/(label+'.lean');source.write_text(self.mod.render('context','code','target',nonce))
            measurement={'target':'target','raw':1,'scaled':0,'axioms':[]}
            text='REFACTOR_EVAL '+nonce+' '+json.dumps(measurement) if i else ''
            log=source.with_suffix('.log');log.write_text(text)
            rec={'source':source.name,'source_sha256':m.sha(source.read_bytes()),'log':log.name,'log_sha256':m.sha(log.read_bytes()),'command':['lean','--root='+str(folder.resolve()),str(source.resolve())],'returncode':0,'timed_out':False}
            if i:rec['measurement']=measurement
            self.result['environments']['v']['runs'].append(rec)
        self.save()
    def save(self):m.write(self.directory/'result.json',self.result)
    def check(self):return m.cached_verification(self.mod,self.env,'code',self.problem,self.directory,3)
    def test_matching_completed_receipt_reused(self):self.assertTrue(self.check()['valid'])
    def test_wrong_candidate_rejected(self):
        with self.assertRaises(ValueError):m.cached_verification(self.mod,self.env,'other',self.problem,self.directory,3)
    def test_context_change_rejected(self):
        self.env['template']='changed'
        with self.assertRaises(ValueError):self.check()
    def test_log_tampering_rejected(self):
        (self.directory/'v/check.log').write_text('changed')
        with self.assertRaises(ValueError):self.check()
    def test_measurement_tampering_rejected(self):
        self.result['environments']['v']['runs'][1]['measurement']['raw']=999;self.save()
        with self.assertRaises(ValueError):self.check()
    def test_partial_success_not_reused(self):
        self.result['environments']['v']['runs'].pop();self.save()
        with self.assertRaises(ValueError):self.check()
if __name__=='__main__':unittest.main()

class OrderTests(unittest.TestCase):
    def test_failed_version_first_without_dropping_versions(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);out=root/'next'
            m.write(root/'c001/result.json',{'environments':{'old':{'valid':False,'error':{'kind':'compile'}}}})
            envs=[{'id':'primary'},{'id':'old'},{'id':'other'}]
            self.assertEqual([e['id'] for e in m.verification_order(envs,out)],['old','primary','other'])
            self.assertEqual(envs,[{'id':'primary'},{'id':'old'},{'id':'other'}])
    def test_resource_failure_does_not_change_default_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            m.write(root/'c001/result.json',{'environments':{'old':{'valid':False,'error':{'kind':'timeout'}}}})
            envs=[{'id':'primary'},{'id':'old'}]
            self.assertEqual(m.verification_order(envs,root/'next'),envs)
