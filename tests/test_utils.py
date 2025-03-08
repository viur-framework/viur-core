from datetime import timedelta as td

from abstract import ViURTestCase

S = "Mein Kumpel aus 's-Hertogenbosch, meinte:\n" \
    "<strong>\"So ein Feuerball, Jungeee!\"</strong>\n" \
    "(=> vgl. New Kids)"
E = "Mein Kumpel aus &#39;s-Hertogenbosch, meinte: " \
    "&lt;strong&gt;&quot;So ein Feuerball, Jungeee!&quot;&lt;/strong&gt; " \
    "&#40;&#61;&gt; vgl. New Kids&#41;"""


class TestUtils(ViURTestCase):

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

    def test_json(self):
        from viur.core import utils
        import datetime

        # key = db.Key("test", "hello world")
        now = datetime.datetime.fromisoformat("2024-02-28T14:43:17.125207+00:00")
        duration = datetime.timedelta(minutes=13, microseconds=37)

        example = {
            "datetime": now,
            "false": False,
            "float": 42.5,
            "generator": (x for x in "Hello"),
            "int": 1337,
            # "key": key, # cannot use in tests
            "list": [1, 2, 3],
            "none": None,
            "set": {1, 2, 3},
            "str": "World",
            "timedelta": duration,
            "true": True,
            "tuple": (1, 2, 3),
        }

        # serialize example into string
        s = utils.json.dumps(example)

        # check if string is as expected
        self.assertEqual(
            s,
            """{"datetime": {".__datetime__": "2024-02-28T14:43:17.125207+00:00"}, "false": false, "float": 42.5, "generator": ["H", "e", "l", "l", "o"], "int": 1337, "list": [1, 2, 3], "none": null, "set": {".__set__": [1, 2, 3]}, "str": "World", "timedelta": {".__timedelta__": 780000037.0}, "true": true, "tuple": [1, 2, 3]}""",  # noqa
        )

        # deserialize string into object again
        o = utils.json.loads(s)

        # patch tuple as a list
        example["tuple"] = list(example["tuple"])
        example["generator"] = [x for x in "Hello"]

        # self.assertEqual(example, o)
        for k, v in example.items():
            self.assertEqual(o[k], v)

    def test_parse_timedelta(self):
        from viur.core import utils
        self.assertEqual(td(seconds=60), utils.parse.timedelta(td(seconds=60)))
        self.assertEqual(td(seconds=60), utils.parse.timedelta(60))
        self.assertEqual(td(seconds=60), utils.parse.timedelta(60.0))
        self.assertEqual(td(seconds=60), utils.parse.timedelta("60"))
        self.assertEqual(td(seconds=60), utils.parse.timedelta("60.0"))
        self.assertNotEqual(td(seconds=0), utils.parse.timedelta(60.0))
