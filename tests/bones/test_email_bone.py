from abstract import ViURTestCase


class TestEmailBone(ViURTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bone_name = "emailTestBone"

    def assert_valid(self, bone, value):
        res = bone.singleValueFromClient(value, {}, self.bone_name, None)
        self.assertEqual((value, None), res, f"{value!r} should be accepted")

    def assert_invalid(self, bone, value):
        from viur.core.bones import ReadFromClientError, ReadFromClientErrorSeverity
        res = bone.singleValueFromClient(value, {}, self.bone_name, None)
        self.assertIsInstance(res[1], list)
        self.assertTrue(res[1], f"{value!r} should be rejected")
        self.assertIsInstance(rfce := res[1][0], ReadFromClientError)
        self.assertIs(ReadFromClientErrorSeverity.Invalid, rfce.severity)

    def test_singleValueFromClient(self):
        from viur.core.bones import EmailBone
        bone = EmailBone()

        for value in (
            "test@example.com",
            "test@online.de",
            "info@t-online.de",
            "test@sub.domain.co.uk",
            "john.doe+tag@example.com",
            "user@xn--mnchen-3ya.de",  # already IDNA-encoded
            "user@münchen.de",  # unicode domain
            f"test@{'a' * 63}.de",  # label at the 63-char limit
        ):
            self.assert_valid(bone, value)

        for value in (
            "",
            "no-at-sign.de",
            "test@domain",  # missing TLD
            "test@.de",  # empty label
            "test@dom..de",  # empty inner label
            "test@-example.de",  # label with leading hyphen
            "test@example-.de",  # label with trailing hyphen
            "test@-.de",
            "test@exa mple.de",  # space in domain
            "user@127.0.0.1",  # purely numeric TLD / bare IP not supported
            f"test@{'a' * 64}.de",  # label exceeding the 63-char limit
            "test@ex_ample.de",  # underscore is not a valid label character
        ):
            self.assert_invalid(bone, value)
