from datetime import timedelta as td
from unittest import mock

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

    def test_string_unescape_filename_entities(self):
        """unescape() must handle both 2- and 3-digit numeric HTML entities used in filenames."""
        from viur.core import utils
        # short-form: &#40; &#41; &#61;
        self.assertEqual(utils.string.unescape("file&#40;1&#41;&#61;x.pdf"), "file(1)=x.pdf")
        # long-form (leading zero): &#040; &#041; &#061;
        self.assertEqual(utils.string.unescape("file&#040;1&#041;&#061;x.pdf"), "file(1)=x.pdf")
        # mixed
        self.assertEqual(utils.string.unescape("&#040;test&#41;&#061;val"), "(test)=val")

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


def _make_request(url: str):
    """Return a mock mimicking current.request.get() with .request.url set."""
    req = mock.Mock()
    req.request.url = url
    ctx_var = mock.Mock()
    ctx_var.get.return_value = req
    return ctx_var


class TestGetBaseUrl(ViURTestCase):

    def _call(self, url: str, project_id: str = "myproject") -> str:
        from viur.core import utils
        from viur.core import current
        from viur.core.config import conf

        with mock.patch.object(current, "request", _make_request(url)), \
             mock.patch.object(conf.instance, "project_id", project_id):
            return utils.get_base_url()

    # --- localhost variants → http ---

    def test_localhost_plain(self):
        self.assertEqual(self._call("http://localhost:8080/foo"), "http://localhost:8080")

    def test_localhost_no_port(self):
        self.assertEqual(self._call("http://localhost/"), "http://localhost")

    def test_127_0_0_1(self):
        self.assertEqual(self._call("http://127.0.0.1:8080/bar"), "http://127.0.0.1:8080")

    def test_ipv4_all_interfaces(self):
        self.assertEqual(self._call("http://0.0.0.0:8080/"), "http://0.0.0.0:8080")

    def test_ipv6_loopback(self):
        self.assertEqual(self._call("http://[::1]:8080/"), "http://[::1]:8080")

    # --- non-localhost → https ---

    def test_plain_domain(self):
        self.assertEqual(self._call("http://www.example.com/path"), "https://www.example.com")

    def test_already_https(self):
        self.assertEqual(self._call("https://www.example.com/path"), "https://www.example.com")

    def test_subdomain(self):
        self.assertEqual(self._call("https://api.example.com/v1/endpoint"), "https://api.example.com")

    # --- appspot.com dot-replacement ---

    def test_appspot_dot_replaced(self):
        # .myproject. in hostname → -dot-myproject.
        result = self._call(
            "https://default.myproject.appspot.com/",
            project_id="myproject",
        )
        self.assertEqual(result, "https://default-dot-myproject.appspot.com")

    def test_appspot_no_replacement_without_project_id_match(self):
        # project_id does not appear in the host → no replacement
        result = self._call(
            "https://www.example.com/",
            project_id="myproject",
        )
        self.assertEqual(result, "https://www.example.com")
