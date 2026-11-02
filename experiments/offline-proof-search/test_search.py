import unittest
from mutations import split_rules, variants
from search import pareto, rank


class Tests(unittest.TestCase):
    def test_nested_rule_commas(self):
        self.assertEqual(split_rules('foo (a, b), bar [x, y], ← baz'), ['foo (a, b)', 'bar [x, y]', '← baz'])
        self.assertIsNone(split_rules('foo (a, b'))
        self.assertIsNone(split_rules('foo /- , -/, bar'))

    def test_statement_unchanged_and_distinct(self):
        statement = 'theorem t (h : True) : True := '
        code = statement + 'by\n  simp only [foo (a, b), bar] (F := F)\n'
        out = variants(code, statement)
        self.assertTrue(all(c.startswith(statement) for _, c in out))
        self.assertEqual(len(out), len({c for _, c in out}))
        self.assertTrue(any('[foo (a, b)]' in c for _,c in out))
        self.assertTrue(any('[]' in c for _,c in out))

    def test_tradeoff_and_pareto(self):
        b = {'tokens': 100, 'raw': 10000}
        a = {'tokens': 20, 'raw': 1000}
        c = {'tokens': 10, 'raw': 3000}
        d = {'tokens': 25, 'raw': 2000}
        self.assertLess(rank(a,b), rank(c,b))
        self.assertEqual(pareto([a,c,d]), [a,c])


if __name__ == '__main__':
    unittest.main()
