"""Infrastructure recovery must not duplicate an evaluated proposal."""
from pathlib import Path
import tempfile
import unittest
from resume_preflight import digest, validate_pending


class PendingSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.evidence={'step':2,'files':{}}
        for name in ('states/001.json','responses/002.json','steps/002/response.json',
                     'steps/002/candidate.lean','requests/002.json'):
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(name);self.evidence['files'][name]=digest(path)

    def test_unevaluated_identical_files_can_resume(self):
        validate_pending(self.root,self.evidence)

    def test_changed_candidate_is_rejected(self):
        (self.root/'steps/002/candidate.lean').write_text('another candidate')
        with self.assertRaisesRegex(AssertionError,'Pending file changed'):
            validate_pending(self.root,self.evidence)

    def test_existing_evaluation_blocks_retry(self):
        (self.root/'steps/002/evaluation').mkdir()
        with self.assertRaisesRegex(AssertionError,'Already evaluated'):
            validate_pending(self.root,self.evidence)

    def test_advanced_state_blocks_retry(self):
        (self.root/'states/002.json').write_text('advanced')
        with self.assertRaises(AssertionError):validate_pending(self.root,self.evidence)


if __name__=='__main__':unittest.main()
