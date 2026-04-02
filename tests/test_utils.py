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

    def test_parse_bool(self):
        from viur.core import utils
        # truthy values (default set)
        for v in ("true", "True", "TRUE", " true ", "yes", "Yes", "YES", "1", " 1 "):
            self.assertTrue(utils.parse.bool(v), msg=repr(v))
        # falsy values
        for v in ("false", "False", "no", "NO", "0", "", "maybe", "2", None, 0, False):
            self.assertFalse(utils.parse.bool(v), msg=repr(v))
        # custom truthy set
        self.assertTrue(utils.parse.bool("ok", truthy_values=("ok",)))
        self.assertFalse(utils.parse.bool("yes", truthy_values=("ok",)))

    def test_parse_sortorder(self):
        from viur.core import utils
        from viur.core.db import SortOrder
        # ascending is the default/catch-all
        for v in ("asc", "ascending", "0", "blah", "", None):
            self.assertEqual(SortOrder.Ascending, utils.parse.sortorder(v), msg=repr(v))
        # descending
        for v in ("desc", "descending", "1", "DESC"):
            self.assertEqual(SortOrder.Descending, utils.parse.sortorder(v), msg=repr(v))
        # inverted ascending
        for v in ("inverted_asc", "inverted_ascending", "2"):
            self.assertEqual(SortOrder.InvertedAscending, utils.parse.sortorder(v), msg=repr(v))
        # inverted descending
        for v in ("inverted_desc", "inverted_descending", "3"):
            self.assertEqual(SortOrder.InvertedDescending, utils.parse.sortorder(v), msg=repr(v))


class TestEnsureIterable(ViURTestCase):

    def test_list_passthrough(self):
        from viur.core.utils import ensure_iterable
        self.assertEqual([1, 2, 3], list(ensure_iterable([1, 2, 3])))

    def test_tuple_passthrough(self):
        from viur.core.utils import ensure_iterable
        self.assertEqual((1, 2), tuple(ensure_iterable((1, 2))))

    def test_none_returns_empty(self):
        from viur.core.utils import ensure_iterable
        self.assertEqual((), tuple(ensure_iterable(None)))

    def test_empty_string_returns_empty(self):
        from viur.core.utils import ensure_iterable
        self.assertEqual((), tuple(ensure_iterable("")))

    def test_non_empty_string_wraps(self):
        from viur.core.utils import ensure_iterable
        # strings are not treated as iterables — wrapped in a tuple
        self.assertEqual(("hello",), tuple(ensure_iterable("hello")))

    def test_scalar_wraps_in_tuple(self):
        from viur.core.utils import ensure_iterable
        self.assertEqual((42,), tuple(ensure_iterable(42)))

    def test_callable_is_called(self):
        from viur.core.utils import ensure_iterable
        self.assertEqual([1, 2], list(ensure_iterable(lambda: [1, 2])))

    def test_callable_disabled(self):
        from viur.core.utils import ensure_iterable

        def fn():
            return [1, 2]

        # with allow_callable=False the lambda itself is wrapped, not called
        result = tuple(ensure_iterable(fn, allow_callable=False))
        self.assertEqual((fn,), result)

    def test_test_callback_filters(self):
        from viur.core.utils import ensure_iterable
        # test=lambda x: False → empty tuple
        self.assertEqual((), tuple(ensure_iterable([1, 2, 3], test=lambda x: False)))
        # test=lambda x: True → pass through
        self.assertEqual([1, 2, 3], list(ensure_iterable([1, 2, 3], test=lambda x: True)))


class TestBuildContentDisposition(ViURTestCase):

    def test_attachment_ascii(self):
        from viur.core.utils import build_content_disposition_header
        result = build_content_disposition_header("report.pdf", attachment=True)
        self.assertIn("attachment", result)
        self.assertIn('filename="report.pdf"', result)
        self.assertIn("filename*=UTF-8''report.pdf", result)

    def test_inline_flag(self):
        from viur.core.utils import build_content_disposition_header
        result = build_content_disposition_header("img.png", inline=True)
        self.assertIn("inline", result)
        self.assertNotIn("attachment", result)

    def test_unicode_filename_encoded(self):
        from viur.core.utils import build_content_disposition_header
        result = build_content_disposition_header("Änderung.pdf", attachment=True)
        # ASCII fallback strips umlaut
        self.assertIn('filename="Anderung.pdf"', result)
        # UTF-8 encoded version present
        self.assertIn("%C3%84nderung.pdf", result)

    def test_both_flags_raises(self):
        from viur.core.utils import build_content_disposition_header
        with self.assertRaises(ValueError):
            build_content_disposition_header("f.pdf", attachment=True, inline=True)

    def test_no_disposition_type(self):
        from viur.core.utils import build_content_disposition_header
        result = build_content_disposition_header("f.pdf")
        self.assertNotIn("attachment", result)
        self.assertNotIn("inline", result)
        self.assertIn('filename="f.pdf"', result)


class TestStringUtils(ViURTestCase):

    def test_normalize_ascii(self):
        from viur.core.utils import string
        self.assertEqual("Anderung", string.normalize_ascii("Änderung"))
        self.assertEqual("Cafe", string.normalize_ascii("Café"))
        self.assertEqual("ascii", string.normalize_ascii("ascii"))

    def test_is_prefix(self):
        from viur.core.utils import string
        handler = "tree.file.special"
        self.assertTrue(string.is_prefix(handler, "tree"))
        self.assertTrue(string.is_prefix(handler, "tree.file"))
        self.assertTrue(string.is_prefix(handler, "tree.file.special"))
        self.assertFalse(string.is_prefix(handler, "tree.node"))
        self.assertFalse(string.is_prefix(handler, "tree.files"))
        # exact match
        self.assertTrue(string.is_prefix("tree", "tree"))
        # custom delimiter
        self.assertTrue(string.is_prefix("a/b/c", "a/b", delimiter="/"))
        self.assertFalse(string.is_prefix("a/b/c", "a.b", delimiter="/"))

    def test_random_length(self):
        from viur.core.utils import string
        for length in (1, 10, 32):
            r = string.random(length)
            self.assertEqual(length, len(r))
            self.assertTrue(r.isalnum())
