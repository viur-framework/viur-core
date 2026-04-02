from abstract import ViURTestCase


class TestEncodePassword(ViURTestCase):

    def test_returns_dict_with_expected_keys(self):
        from viur.core.bones.password import encode_password
        result = encode_password("secret", "somesalt")
        self.assertIn("pwhash", result)
        self.assertIn("salt", result)
        self.assertIn("iterations", result)
        self.assertIn("dklen", result)

    def test_same_input_same_output(self):
        from viur.core.bones.password import encode_password
        a = encode_password("secret", "somesalt")
        b = encode_password("secret", "somesalt")
        self.assertEqual(a["pwhash"], b["pwhash"])

    def test_different_salts_different_hashes(self):
        from viur.core.bones.password import encode_password
        a = encode_password("secret", "salt1")
        b = encode_password("secret", "salt2")
        self.assertNotEqual(a["pwhash"], b["pwhash"])

    def test_pwhash_is_hex_bytes(self):
        from viur.core.bones.password import encode_password
        result = encode_password("secret", "somesalt")
        self.assertIsInstance(result["pwhash"], bytes)
        # must be valid hex
        bytes.fromhex(result["pwhash"].decode())


class TestPasswordBoneIsInvalid(ViURTestCase):

    def setUp(self):
        super().setUp()
        from viur.core.bones.password import PasswordBone
        self.bone = PasswordBone()

    def test_empty_string_is_valid(self):
        # Empty password is handled by fromClient, not isInvalid
        self.assertFalse(self.bone.isInvalid(""))

    def test_strong_password_is_valid(self):
        self.assertFalse(self.bone.isInvalid("Abc123!xyz"))

    def test_too_short_fails(self):
        # fewer than 8 chars → required test fails
        result = self.bone.isInvalid("Ab1!")
        self.assertTrue(result)  # returns list of errors

    def test_missing_uppercase_below_threshold(self):
        # only lowercase + length (required) → 2/5 tests pass, below threshold of 4
        result = self.bone.isInvalid("abcdefgh")
        self.assertTrue(result)  # below threshold

    def test_all_optional_pass(self):
        # uppercase + lowercase + digit + special + length ≥ 8
        self.assertFalse(self.bone.isInvalid("Password1!"))

    def test_custom_threshold_zero(self):
        from viur.core.bones.password import PasswordBone
        bone = PasswordBone(test_threshold=0)
        # threshold=0 → optional tests don't matter; required length test still applies
        # Use a long-enough password so the required test (≥8 chars) passes
        self.assertFalse(bone.isInvalid("weakpassword"))

    def test_no_tests(self):
        from viur.core.bones.password import PasswordBone
        bone = PasswordBone(tests=(), test_threshold=0)
        self.assertFalse(bone.isInvalid("anything"))


class TestPasswordBoneFromClient(ViURTestCase):

    def setUp(self):
        super().setUp()
        from viur.core.bones.password import PasswordBone
        self.bone = PasswordBone()

    def test_field_missing_returns_notset(self):
        from viur.core.bones.base import ReadFromClientErrorSeverity
        errs = self.bone.fromClient({}, "password", {})
        self.assertIsNotNone(errs)
        self.assertEqual(ReadFromClientErrorSeverity.NotSet, errs[0].severity)

    def test_empty_value_returns_empty(self):
        from viur.core.bones.base import ReadFromClientErrorSeverity
        errs = self.bone.fromClient({}, "password", {"password": ""})
        self.assertIsNotNone(errs)
        self.assertEqual(ReadFromClientErrorSeverity.Empty, errs[0].severity)

    def test_weak_password_returns_invalid(self):
        from viur.core.bones.base import ReadFromClientErrorSeverity
        errs = self.bone.fromClient({}, "password", {"password": "weak"})
        self.assertIsNotNone(errs)
        self.assertEqual(ReadFromClientErrorSeverity.Invalid, errs[0].severity)

    def test_strong_password_stored_as_hash(self):
        skel = {}
        errs = self.bone.fromClient(skel, "password", {"password": "StrongPass1!"})
        self.assertIsNone(errs)
        self.assertIsInstance(skel["password"], dict)
        self.assertIn("pwhash", skel["password"])

    def test_raw_mode_stores_plaintext(self):
        from viur.core.bones.password import PasswordBone
        bone = PasswordBone(raw=True)
        skel = {}
        errs = bone.fromClient(skel, "password", {"password": "StrongPass1!"})
        self.assertIsNone(errs)
        self.assertEqual("StrongPass1!", skel["password"])
