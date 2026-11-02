import unittest
from lookup import header_imports


class HeaderTests(unittest.TestCase):
    def test_nested_comments_and_code_are_not_imports(self):
        text = '/- import Bad /- import Worse -/ -/\nmodule\npublic import A.B\nimport all C\n'
        text += 'def s := "import Fake"\nimport AlsoFake\n'
        self.assertEqual(header_imports(text), ['A.B', 'C'])


if __name__ == '__main__':
    unittest.main()
