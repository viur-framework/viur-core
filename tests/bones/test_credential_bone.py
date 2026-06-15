from abstract import ViURTestCase


class TestCredentialBoneInit(ViURTestCase):

    def test_default_init(self):
        from viur.core.bones.credential import CredentialBone
        bone = CredentialBone()
        self.assertIsNone(bone.max_length)

    def test_multiple_raises(self):
        from viur.core.bones.credential import CredentialBone
        with self.assertRaises(ValueError):
            CredentialBone(multiple=True)

    def test_languages_raises(self):
        from viur.core.bones.credential import CredentialBone
        with self.assertRaises(ValueError):
            CredentialBone(languages=["de", "en"])


class TestCredentialBoneIsInvalid(ViURTestCase):

    def test_none_is_valid(self):
        from viur.core.bones.credential import CredentialBone
        bone = CredentialBone()
        self.assertFalse(bone.isInvalid(None))

    def test_any_length_without_limit(self):
        from viur.core.bones.credential import CredentialBone
        bone = CredentialBone()
        self.assertIsNone(bone.isInvalid("x" * 10_000))

    def test_within_max_length(self):
        from viur.core.bones.credential import CredentialBone
        bone = CredentialBone(max_length=10)
        self.assertIsNone(bone.isInvalid("short"))

    def test_exceeds_max_length(self):
        from viur.core.bones.credential import CredentialBone
        bone = CredentialBone(max_length=5)
        self.assertIsNotNone(bone.isInvalid("toolong"))

    def test_exact_max_length_is_valid(self):
        from viur.core.bones.credential import CredentialBone
        bone = CredentialBone(max_length=5)
        self.assertIsNone(bone.isInvalid("exact"))


class TestCredentialBoneSingleValueFromClient(ViURTestCase):

    def _from_client(self, bone, value):
        return bone.singleValueFromClient(value, {}, "secret", {})

    def test_valid_value_returned(self):
        from viur.core.bones.credential import CredentialBone
        bone = CredentialBone()
        val, err = self._from_client(bone, "api-key-123")
        self.assertIsNone(err)
        self.assertEqual("api-key-123", val)

    def test_too_long_returns_error(self):
        from viur.core.bones.credential import CredentialBone
        bone = CredentialBone(max_length=5)
        val, err = self._from_client(bone, "toolongvalue")
        self.assertIsNotNone(err)
        self.assertEqual(bone.getEmptyValue(), val)


class TestCredentialBoneUnserialize(ViURTestCase):

    def test_always_returns_empty_dict(self):
        from viur.core.bones.credential import CredentialBone
        bone = CredentialBone()
        self.assertEqual({}, bone.unserialize({"secret": "stored"}, "secret"))
