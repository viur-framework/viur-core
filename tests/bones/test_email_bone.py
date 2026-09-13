from abstract import ViURTestCase


class TestEmailBone(ViURTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bone_name = "emailTestBone"

    def setUp(self):
        super().setUp()
        from viur.core.bones import EmailBone
        self.bone = EmailBone()

    def assert_valid(self, value):
        res = self.bone.singleValueFromClient(value, {}, self.bone_name, None)
        self.assertEqual((value, None), res, f"{value!r} should be accepted")

    def assert_invalid(self, value):
        from viur.core.bones import ReadFromClientError, ReadFromClientErrorSeverity
        _, errors = self.bone.singleValueFromClient(value, {}, self.bone_name, None)
        self.assertIsInstance(errors, list)
        assert errors, f"{value!r} should be rejected"
        rfce = errors[0]
        self.assertIsInstance(rfce, ReadFromClientError)
        self.assertIs(ReadFromClientErrorSeverity.Invalid, rfce.severity)

    def test_singleValueFromClient(self):
        for value in (
            "test@example.com",
            "test@online.de",
            "info@t-online.de",
            "test@sub.domain.co.uk",
            "john.doe+tag@example.com",
            "user@xn--mnchen-3ya.de",  # already IDNA-encoded
            "user@münchen.de",  # unicode domain
            f"test@{'a' * 63}.de",  # label at the 63-char limit
            "user+tag@example.com",  # plus addressing
            "user.name+filter_123@example.org",  # special chars in local part
            "éuser@example.com",  # unicode local part (U+0080+) is explicitly allowed
        ):
            self.assert_valid(value)

        for value in (
            "",
            None,
            "no-at-sign.de",
            "userexample.com",  # missing @
            "user@",  # missing domain
            "test@domain",  # missing TLD
            "user@@example.com",  # double @
            "a" * 65 + "@example.com",  # local part > 64 chars
            "user@" + "a" * 250 + ".com",  # total > 255 chars
            "test@.de",  # empty label
            "test@dom..de",  # empty inner label
            "user@exa mple.com",  # space in domain
            "test@-example.de",  # label with leading hyphen
            "test@example-.de",  # label with trailing hyphen
            "test@-.de",
            "user@127.0.0.1",  # purely numeric TLD / bare IP not supported
            f"test@{'a' * 64}.de",  # label exceeding the 63-char limit
            "test@ex_ample.de",  # underscore is not a valid label character
            "first..last@example.com",  # RFC 5321: consecutive dots in local part are forbidden
            ".user@example.com",  # leading dot in local part
            "user.@example.com",  # trailing dot in local part
            "first last@example.com",  # space in local part
            " user@example.com",  # leading space
            "user@example.com ",  # trailing space
        ):
            self.assert_invalid(value)
