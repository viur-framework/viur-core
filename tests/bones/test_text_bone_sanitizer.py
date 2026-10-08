"""
Tests for the HTML sanitizer behind :class:`viur.core.bones.text.TextBone`.

HtmlSerializer is the security-relevant part of the bone: it decides which tags,
attributes, styles and classes survive a round-trip from client input.
"""
from abstract import ViURTestCase

VALID_HTML = {
    "validTags": ["p", "b", "a", "img", "div", "br"],
    "validAttrs": {
        "a": ["href", "target", "title"],
        "img": ["src", "alt"],
        "div": ["class", "style"],
        "p": ["class", "style"],
    },
    "validStyles": ["color", "text-align"],
    "validClasses": ["highlight", "col-*"],
    "singleTags": ["br", "img"],
}


_DEFAULT = object()


class SanitizerTestCase(ViURTestCase):

    def setUp(self):
        super().setUp()
        from unittest import mock

        from viur.core import conf

        # handle_starttag reaches for conf.main_app.json when it sees a src attribute
        # and does not guard against main_app being unset, so give it a stub.
        self._main_app = conf.main_app
        conf.main_app = mock.Mock(json=mock.Mock(spec=[]))
        self.addCleanup(setattr, conf, "main_app", self._main_app)

    def _clean(self, html, valid=_DEFAULT, srcSet=None):
        from viur.core.bones.text import HtmlSerializer

        return HtmlSerializer(VALID_HTML if valid is _DEFAULT else valid, srcSet=srcSet).sanitize(html)


class TestTagFiltering(SanitizerTestCase):

    def test_a_valid_tag_survives(self):
        self.assertEqual("<p>text</p>", self._clean("<p>text</p>"))

    def test_an_invalid_tag_is_dropped_but_its_text_is_kept(self):
        self.assertIn("text", self._clean("<script>text</script>"))
        self.assertNotIn("<script>", self._clean("<script>text</script>"))

    def test_an_empty_valid_tag_is_discarded(self):
        self.assertEqual("", self._clean("<p></p>"))

    def test_a_single_tag_survives_without_content(self):
        self.assertIn("<br>", self._clean("<br>"))

    def test_nested_tags_survive(self):
        self.assertEqual("<p><b>bold</b></p>", self._clean("<p><b>bold</b></p>"))

    def test_unclosed_tags_are_closed(self):
        self.assertEqual("<p>text</p>", self._clean("<p>text"))

    def test_a_stray_end_tag_is_ignored(self):
        self.assertEqual("text", self._clean("text</p>"))

    def test_without_a_config_every_tag_is_stripped(self):
        self.assertNotIn("<", self._clean("<p>text</p>", valid=None))

    def test_special_characters_in_text_are_escaped(self):
        result = self._clean("<p>a &lt; b</p>")

        self.assertNotIn("<b", result.replace("<b>", ""))


class TestAttributeFiltering(SanitizerTestCase):

    def test_a_valid_attribute_survives(self):
        self.assertIn('href="/page"', self._clean('<a href="/page">x</a>'))

    def test_an_attribute_invalid_for_that_tag_is_dropped(self):
        self.assertNotIn("href", self._clean('<p href="/page">x</p>'))

    def test_an_attribute_on_an_unknown_tag_is_dropped(self):
        self.assertNotIn("href", self._clean('<b href="/page">x</b>'))

    def test_event_handlers_are_dropped(self):
        self.assertNotIn("onclick", self._clean('<a onclick="evil()">x</a>'))

    def test_javascript_urls_are_dropped(self):
        self.assertNotIn("javascript", self._clean('<a href="javascript:evil()">x</a>').lower())

    def test_blank_targets_get_a_noopener_rel(self):
        result = self._clean('<a href="/x" target="_blank">x</a>')

        self.assertIn('rel="noopener noreferrer"', result)

    def test_a_normal_target_gets_no_rel(self):
        self.assertNotIn("noopener", self._clean('<a href="/x" target="_self">x</a>'))

    def test_href_may_contain_parentheses_and_at_signs(self):
        """title/href/alt are exempt from the general character filter."""
        self.assertIn("href", self._clean('<a href="/a(b)@c">x</a>'))

    def test_a_quote_in_href_is_still_rejected(self):
        self.assertNotIn("href", self._clean("""<a href="/a'b">x</a>"""))

    def test_an_attribute_value_with_forbidden_characters_is_dropped(self):
        """Only title/href/alt are exempt - target is not."""
        self.assertNotIn("target", self._clean('<a href="/x" target="a(b)">x</a>'))

    def test_alt_is_exempt_like_title_and_href(self):
        self.assertIn("alt", self._clean('<img src="/a.png" alt="a(b)">'))


class TestSrcFiltering(SanitizerTestCase):

    def test_an_absolute_http_src_survives(self):
        self.assertIn("src", self._clean('<img src="http://example.com/a.png">'))

    def test_an_https_src_survives(self):
        self.assertIn("src", self._clean('<img src="https://example.com/a.png">'))

    def test_a_root_relative_src_survives(self):
        self.assertIn("src", self._clean('<img src="/a.png">'))

    def test_a_relative_src_is_dropped(self):
        self.assertNotIn("src", self._clean('<img src="a.png">'))

    def test_a_data_uri_src_is_dropped(self):
        self.assertNotIn("src", self._clean('<img src="data:image/png;base64,AAA">'))


class TestStyleFiltering(SanitizerTestCase):

    def test_a_valid_style_survives(self):
        self.assertIn("color: red", self._clean('<div style="color: red">x</div>'))

    def test_an_invalid_style_is_dropped(self):
        self.assertNotIn("position", self._clean('<div style="position: absolute">x</div>'))

    def test_ie_expressions_are_dropped(self):
        self.assertNotIn("expression", self._clean('<div style="color: expression(evil())">x</div>').lower())

    def test_css_imports_are_dropped(self):
        self.assertNotIn("import", self._clean('<div style="color: import(evil)">x</div>').lower())

    def test_several_styles_survive_together(self):
        result = self._clean('<div style="color: red; text-align: left">x</div>')

        self.assertIn("color: red", result)
        self.assertIn("text-align: left", result)

    def test_a_style_with_forbidden_characters_is_dropped(self):
        self.assertNotIn("color", self._clean('<div style="color: red(1)">x</div>'))

    def test_a_tag_with_only_invalid_styles_gets_no_style_attribute(self):
        self.assertNotIn("style", self._clean('<div style="position: absolute">x</div>'))


class TestClassFiltering(SanitizerTestCase):

    def test_a_whitelisted_class_survives(self):
        self.assertIn('class="highlight"', self._clean('<div class="highlight">x</div>'))

    def test_an_unknown_class_is_dropped(self):
        self.assertNotIn("class", self._clean('<div class="evil">x</div>'))

    def test_a_prefix_whitelisted_class_survives(self):
        self.assertIn('class="col-6"', self._clean('<div class="col-6">x</div>'))

    def test_a_class_with_invalid_characters_is_dropped(self):
        self.assertNotIn("class", self._clean('<div class="high light!">x</div>'))

    def test_valid_and_invalid_classes_are_separated(self):
        result = self._clean('<div class="highlight evil">x</div>')

        self.assertIn("highlight", result)
        self.assertNotIn("evil", result)


class TestEntityHandling(SanitizerTestCase):

    def _clean_raw(self, html):
        from viur.core.bones.text import HtmlSerializer

        # convert_charrefs=False so the parser reports the references separately
        return HtmlSerializer(VALID_HTML, convert_charrefs=False).sanitize(html)

    def test_a_character_reference_is_kept(self):
        self.assertIn("&#169;", self._clean_raw("<p>&#169;</p>"))

    def test_a_known_entity_reference_is_kept(self):
        self.assertIn("&nbsp;", self._clean_raw("<p>&nbsp;</p>"))

    def test_an_unknown_entity_reference_is_dropped(self):
        self.assertNotIn("&notanentity;", self._clean_raw("<p>&notanentity;</p>"))


class TestBlobKeyCollection(SanitizerTestCase):

    def test_a_document_without_files_yields_nothing(self):
        from viur.core.bones.text import CollectBlobKeys

        collector = CollectBlobKeys()
        collector.feed('<p>text</p><img src="/static/a.png">')

        self.assertEqual(set(), collector.blobs)

    def test_tags_without_a_src_are_ignored(self):
        from viur.core.bones.text import CollectBlobKeys

        collector = CollectBlobKeys()
        collector.feed('<a href="/x">text</a>')

        self.assertEqual(set(), collector.blobs)


class TestStyleKeywordFiltering(SanitizerTestCase):

    def test_an_expression_keyword_without_parentheses_is_dropped(self):
        """The parenthesised form never reaches the style parser - the attribute
        filter rejects "(" one level up - so this is the form that exercises it."""
        self.assertNotIn("color", self._clean('<div style="color: expression">x</div>'))

    def test_an_import_keyword_without_parentheses_is_dropped(self):
        self.assertNotIn("color", self._clean('<div style="color: import">x</div>'))

    def test_the_keyword_check_matches_on_the_prefix_only(self):
        """"importantly" starts with "import" and is dropped too - the check is a
        prefix match, not a word match."""
        self.assertNotIn("color", self._clean('<div style="color: importantly">x</div>'))

    def test_an_unrelated_value_survives(self):
        self.assertIn("color: red", self._clean('<div style="color: red">x</div>'))


class TestSrcSetRewriting(SanitizerTestCase):
    """With a srcSet configured, a recognised file src is rewritten and gains a srcSet."""

    def setUp(self):
        super().setUp()
        from unittest import mock

        from viur.core import conf

        # the base class pins vi to spec=[]; these tests need a real file module
        conf.main_app = mock.Mock()

    def _clean_with_files(self, html, srcSet=None, dlkey="dk1"):
        from unittest import mock

        from viur.core import conf
        from viur.core.bones.text import HtmlSerializer

        conf.main_app.json.file.parse_download_url.return_value = mock.Mock(
            dlkey=dlkey, filename="a.png", is_derived=False)
        conf.main_app.json.file.create_download_url.return_value = "/rewritten/a.png"
        conf.main_app.json.file.create_src_set.return_value = "/rewritten/a.png 100w"

        return HtmlSerializer(VALID_HTML, srcSet=srcSet).sanitize(html)

    def test_a_recognised_file_src_is_rewritten(self):
        result = self._clean_with_files('<img src="/file/dk1">')

        self.assertIn("/rewritten/a.png", result)

    def test_a_srcset_is_injected(self):
        result = self._clean_with_files('<img src="/file/dk1">', srcSet={"width": [100]})

        self.assertIn("srcSet=", result)
        self.assertIn("100w", result)

    def test_without_a_srcset_no_srcset_attribute_is_added(self):
        result = self._clean_with_files('<img src="/file/dk1">')

        self.assertNotIn("srcSet=", result)

    def test_an_unrecognised_src_is_left_as_is(self):
        from viur.core import conf
        from viur.core.bones.text import HtmlSerializer

        conf.main_app.json.file.parse_download_url.return_value = None

        result = HtmlSerializer(VALID_HTML, srcSet={"width": [100]}).sanitize('<img src="/static/a.png">')

        self.assertIn("/static/a.png", result)
        self.assertNotIn("srcSet=", result)


class TestEndTagHandling(SanitizerTestCase):
    """handle_endtag walks the pending-tag cache and the open-tag stack."""

    def test_an_end_tag_for_a_cached_empty_element_drops_the_cache(self):
        self.assertEqual("", self._clean("<p></p>"))

    def test_an_end_tag_drops_only_up_to_its_own_start(self):
        result = self._clean("<div><p></p>text</div>")

        self.assertIn("text", result)
        self.assertNotIn("<p>", result)

    def test_an_end_tag_for_an_open_element_closes_it(self):
        self.assertEqual("<p>text</p>", self._clean("<p>text</p>"))

    def test_an_end_tag_closes_every_element_up_to_itself(self):
        result = self._clean("<div><p>text</div>")

        self.assertIn("</p>", result)
        self.assertIn("</div>", result)

    def test_an_end_tag_for_an_unopened_element_is_ignored(self):
        self.assertEqual("<p>text</p>", self._clean("<p>text</p></div>"))

    def test_an_end_tag_while_nothing_is_cached_or_open_is_ignored(self):
        self.assertEqual("text", self._clean("text</p>"))

    def test_nested_empty_elements_collapse(self):
        self.assertEqual("", self._clean("<div><p></p></div>"))


class TestEndTagCacheWalk(SanitizerTestCase):
    """The cache holds opened-but-empty tags; an end tag walks it back."""

    def test_an_end_tag_for_an_uncached_uncopened_element_is_ignored(self):
        result = self._clean("<p><div></b>text</div></p>")

        self.assertIn("text", result)

    def test_an_end_tag_closes_an_open_element_past_several_cached_ones(self):
        """div is open (it has content); p and b are cached and empty. Closing div
        has to walk the whole cache without a match, then close div itself."""
        result = self._clean("<div>text<p><b></div>")

        self.assertIn("text", result)
        self.assertIn("</div>", result)
        self.assertNotIn("<b>", result)

    def test_the_cache_is_walked_back_to_the_matching_start(self):
        result = self._clean("<div><p><b></b></p>text</div>")

        self.assertIn("text", result)
        self.assertNotIn("<b>", result)
