from abstract import ViURTestCase


class TestEmailBoneIsInvalid(ViURTestCase):
    """EmailBone.isInvalid: syntactic email validation."""

    def setUp(self):
        super().setUp()
        from viur.core.bones.email import EmailBone
        self.bone = EmailBone()

    def _valid(self, value):
        self.assertIsNone(self.bone.isInvalid(value), msg=f"{value!r} should be valid")

    def _invalid(self, value):
        self.assertIsNotNone(self.bone.isInvalid(value), msg=f"{value!r} should be invalid")

    # --- valid addresses ---

    def test_simple_address(self):
        self._valid("user@example.com")

    def test_subdomain(self):
        self._valid("user@mail.example.co.uk")

    def test_plus_addressing(self):
        self._valid("user+tag@example.com")

    def test_special_chars_in_local(self):
        self._valid("user.name+filter_123@example.org")

    def test_unicode_local(self):
        # Unicode characters in local part (U+0080+) are explicitly allowed
        self._valid("\u00e9user@example.com")

    def test_hyphen_inside_label(self):
        self._valid("user@t-online.de")

    def test_unicode_domain(self):
        # IDNA domain given as unicode
        self._valid("user@m\u00fcnchen.de")

    def test_idna_encoded_domain(self):
        # IDNA domain already given in punycode
        self._valid("user@xn--mnchen-3ya.de")

    def test_label_at_length_limit(self):
        # a label of exactly 63 characters is allowed
        self._valid(f"user@{'a' * 63}.de")

    # --- invalid addresses ---

    def test_empty_string(self):
        self._invalid("")

    def test_none(self):
        self._invalid(None)

    def test_missing_at(self):
        self._invalid("userexample.com")

    def test_missing_domain(self):
        self._invalid("user@")

    def test_missing_tld(self):
        self._invalid("user@example")

    def test_double_at(self):
        self._invalid("user@@example.com")

    def test_local_too_long(self):
        # local part > 64 chars
        self._invalid("a" * 65 + "@example.com")

    def test_total_too_long(self):
        # total > 255 chars
        self._invalid("user@" + "a" * 250 + ".com")

    def test_space_in_domain(self):
        self._invalid("user@exa mple.com")

    def test_dot_at_start_of_subdomain(self):
        self._invalid("user@.example.com")

    def test_double_dot_in_local_is_invalid(self):
        # RFC 5321: consecutive dots in the local part are forbidden
        self._invalid("first..last@example.com")

    def test_leading_dot_in_local_is_invalid(self):
        self._invalid(".user@example.com")

    def test_trailing_dot_in_local_is_invalid(self):
        self._invalid("user.@example.com")

    def test_space_in_local_is_invalid(self):
        self._invalid("first last@example.com")

    def test_leading_space_is_invalid(self):
        self._invalid(" user@example.com")

    def test_trailing_space_is_invalid(self):
        self._invalid("user@example.com ")

    def test_leading_hyphen_in_label_is_invalid(self):
        # idna.ToASCII does not reject a leading hyphen on its own
        self._invalid("user@-example.de")

    def test_trailing_hyphen_in_label_is_invalid(self):
        self._invalid("user@example-.de")

    def test_label_exceeding_length_limit_is_invalid(self):
        # a label of 64 characters exceeds the RFC 1035 limit
        self._invalid(f"user@{'a' * 64}.de")

    def test_underscore_in_domain_is_invalid(self):
        self._invalid("user@ex_ample.de")

    def test_numeric_tld_is_invalid(self):
        # bare IP addresses / purely numeric TLDs are not accepted
        self._invalid("user@127.0.0.1")
