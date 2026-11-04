import importlib.util
from pathlib import Path
import tempfile
import unittest
from decimal import Decimal
spec=importlib.util.spec_from_file_location('pilot',Path(__file__).with_name('run.py'))
pilot=importlib.util.module_from_spec(spec);spec.loader.exec_module(pilot)

class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.ledger=pilot.Ledger(self.root)
    def settle(self,name,step,amount):
        self.ledger.transact(name,step,reserve=Decimal(amount))
        self.ledger.transact(name,step,raw={'usage':{'cost':amount}})
    def test_boundary_and_problem_isolation(self):
        self.settle('p1',1,'2.50')
        with self.assertRaises(ValueError):self.ledger.transact('p1',2,reserve=Decimal('.01'))
        self.ledger.transact('p2',1,reserve=Decimal('2.50'))
    def test_pending_and_unknown_block_other_problems(self):
        self.ledger.transact('p1',1,reserve=Decimal('.1'))
        with self.assertRaises(ValueError):self.ledger.transact('p2',1,reserve=Decimal('.1'))
        self.ledger.transact('p1',1,raw={})
        with self.assertRaises(ValueError):self.ledger.transact('p2',1,reserve=Decimal('.1'))
    def test_batch_cap(self):
        for i in range(10):self.settle(str(i),1,'2.50')
        with self.assertRaises(ValueError):self.ledger.transact('extra',1,reserve=Decimal('.01'))
    def test_no_redispatch_even_after_settlement(self):
        self.settle('p',1,'.1')
        with self.assertRaises(ValueError):self.ledger.transact('p',1,reserve=Decimal('.1'))
    def test_over_reservation_blocks_batch(self):
        self.ledger.transact('p',1,reserve=Decimal('.1'))
        self.ledger.transact('p',1,raw={'usage':{'cost':'.2'}})
        with self.assertRaises(ValueError):self.ledger.transact('q',1,reserve=Decimal('.1'))
if __name__=='__main__':unittest.main()
