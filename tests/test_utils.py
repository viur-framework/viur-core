import unittest


class TestUtils(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from main import monkey_patch
        monkey_patch()

    def test_escapeString(self):
        from viur.core.utils import escapeString

        self.assertEqual("None", escapeString(None))
        self.assertEqual("abcde", escapeString("abcdefghi", max_length=5))
        self.assertEqual("&lt;html&gt;&&lt;/html&gt;", escapeString("<html>\n&\0</html>"))
