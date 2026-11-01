"""Check the published observations and denominators without Lean or network."""
import json
import tarfile
import unittest

from common import HERE, canonical, read, sha
from corpus import summarize


class PublishedEvidence(unittest.TestCase):
    def test_published_archive_integrity_and_summary(self):
        folder=HERE/'evaluation'
        validation=read(folder/'validation.json')
        archive=folder/'evidence.tar.gz'
        self.assertEqual(sha(archive.read_bytes()),validation['evidence']['sha256'])
        with tarfile.open(archive) as tar:
            members=tar.getmembers()
            self.assertTrue(all(m.isfile() and m.name.startswith('run/') and '..' not in m.name.split('/') for m in members))
            self.assertEqual(len(members),len({m.name for m in members}))
            data={m.name[4:]:tar.extractfile(m).read() for m in members}
        inventory=json.loads(data['artifacts.json'])
        self.assertEqual(sha(data['artifacts.json']),validation['evidence']['inventory_sha256'])
        self.assertEqual(set(data),set(inventory)|{'artifacts.json'})
        for name,digest in inventory.items():
            self.assertEqual(sha(data[name]),digest,name)
        corpus=json.loads(data['corpus.json'])
        self.assertEqual(corpus,read(folder/'corpus.json'))
        self.assertEqual(sha(canonical(corpus)),validation['corpus_sha256'])
        self.assertEqual(json.loads(data['protocol.json']),read(folder/'protocol.json'))
        self.assertEqual(sha((folder/'source-audit.json').read_bytes()),validation['source_audit_sha256'])
        for name,digest in validation['source_files'].items():
            self.assertEqual(sha(data['code/repo/'+name]),digest,name)
        for name,digest in validation['analysis_code'].items():
            self.assertEqual(sha((HERE/name).read_bytes()),digest,name)
        rows=[json.loads(data['cases/'+c['id']+'/result.json']) for c in corpus['cases']]
        summary=summarize(rows)
        published=read(folder/'summary.json')
        for key,value in summary.items():
            self.assertEqual(published[key],value,key)
        derived={r['id']:r for r in read(folder/'rows.json')}
        self.assertEqual(len(derived),49)
        for row in rows:
            table=derived[row['id']]
            self.assertEqual(table['result_sha256'],sha(data['cases/'+row['id']+'/result.json']))
            self.assertEqual(table['final_measured_q'],row['final_q'])
            self.assertEqual(table['selected_q'],2 if row['selected_origin']=='original' and row['final_valid'] else row['final_q'])
        self.assertEqual(published['all_occurrences']['initial_unmeasured'],43)
        self.assertEqual(published['all_occurrences']['failure_not_reproduced'],2)
        self.assertEqual(published['all_occurrences']['recovery_measured'],4)
        self.assertEqual(published['all_occurrences']['recovered'],0)
        self.assertIsNone(published['recursive_repair_effect'])


if __name__=='__main__':
    unittest.main()
