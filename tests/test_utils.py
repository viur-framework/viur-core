import unittest

S = "Mein Kumpel aus 's-Hertogenbosch, meinte:\n" \
    "<strong>\"So ein Feuerball, Jungeee!\"</strong>\n" \
    "(=> vgl. New Kids)"
E = "Mein Kumpel aus &#39;s-Hertogenbosch, meinte: " \
    "&lt;strong&gt;&quot;So ein Feuerball, Jungeee!&quot;&lt;/strong&gt; " \
    "&#40;&#61;&gt; vgl. New Kids&#41;"""


class TestUtils(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from main import monkey_patch
        monkey_patch()

    def test_string_unescape(self):
        from viur.core import utils
        self.assertEqual(utils.string.unescape("Hello&#039;World&#39;s"), "Hello'World's")
        self.assertEqual(utils.string.unescape(E), S.replace("\n", " "))

    def test_string_escape(self):
        from viur.core import utils
        self.assertEqual("None", utils.string.escape(None))
        self.assertEqual("abcde", utils.string.escape("abcdefghi", max_length=5))
        self.assertEqual("&lt;html&gt; &&lt;/html&gt;", utils.string.escape("<html>\n&\0</html>"))
        self.assertEqual(utils.string.escape(S), E)
