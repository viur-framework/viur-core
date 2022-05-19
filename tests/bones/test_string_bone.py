import unittest


class TestStringBone(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		from main import monkey_patch
		monkey_patch()
		cls.bone_name = "myStringBone"

	def test_isEmpty_default_bone(self):
		from viur.core.bones import StringBone
		self._run_tests(bone := StringBone(descr="empty_str"))
		self.assertEqual("", bone.getEmptyValue())
		self.assertIsNone(bone.defaultValue)

	def _run_tests(self, bone):
		# print(bone)
		self.assertFalse(bone.isEmpty(123))
		self.assertFalse(bone.isEmpty("123"))

		self.assertTrue(bone.isEmpty(""))
		self.assertTrue(bone.isEmpty(None))
		self.assertTrue(bone.isEmpty([]))
		self.assertTrue(bone.isEmpty(bone.getEmptyValue()))
		self.assertTrue(bone.isEmpty(str(bone.getEmptyValue())))


class TestStringBone_setBoneValue(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		from main import monkey_patch
		monkey_patch()
		cls.bone_name = "myStringBone"

	def test_setBoneValue_single(self):
		from viur.core.bones import StringBone
		bone = StringBone()
		skel = {}
		self.assertTrue(bone.setBoneValue(skel, self.bone_name, value := "foo", False, None))
		self.assertIn(self.bone_name, skel)
		self.assertEqual(value, skel[self.bone_name])
		# Don't append on multiple bones
		self.assertFalse(bone.multiple)
		with self.assertRaises(AssertionError):
			bone.setBoneValue(skel, self.bone_name, "foo", True, None)
		# Fail with language
		self.assertIsNone(bone.languages)
		with self.assertRaises(AssertionError):
			bone.setBoneValue(skel, self.bone_name, "foo", False, "en")

	def test_setBoneValue_multi(self):
		from viur.core.bones import StringBone
		bone = StringBone(multiple=True)
		skel = {}
		self.assertTrue(bone.setBoneValue(skel, self.bone_name, value := ["foo"], False, None))
		self.assertIn(self.bone_name, skel)
		self.assertListEqual(value, skel[self.bone_name])
		# Append
		self.assertTrue(bone.multiple)
		self.assertTrue(bone.setBoneValue(skel, self.bone_name, "bar", True, None))
		self.assertEqual(["foo", "bar"], skel[self.bone_name])
		# self.assertIs(value, skel[self.bone_name])
		bone.setBoneValue(skel, self.bone_name, "foo", True, None)
		# Fail with language
		self.assertIsNone(bone.languages)
		with self.assertRaises(AssertionError):
			bone.setBoneValue(skel, self.bone_name, "foo", False, "en")


class TestStringBone_fromClient(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		from main import monkey_patch
		monkey_patch()
		cls.bone_name = "myStringBone"

	def test_fromClient_single(self):
		from viur.core.bones import StringBone
		from viur.core.bones.base import ReadFromClientError
		bone = StringBone()
		skel = {}
		data = {self.bone_name: "foo"}
		self.assertIsNone(bone.fromClient(skel, self.bone_name, data))
		self.assertIn(self.bone_name, skel)
		self.assertEqual(data[self.bone_name], skel[self.bone_name])
		# invalid data
		data = {self.bone_name: None}
		self.assertIsInstance(res := bone.fromClient(skel, self.bone_name, data), list)
		self.assertTrue(res)  # list not empty
		self.assertIsInstance(res[0], ReadFromClientError)

	def test_fromClient_multi(self):
		from viur.core.bones import StringBone
		bone = StringBone(multiple=True)
		skel = {}
		data = {self.bone_name: ["foo", "bar"]}
		self.assertIsNone(bone.fromClient(skel, self.bone_name, data))
		self.assertIn(self.bone_name, skel)
		self.assertListEqual(data[self.bone_name], skel[self.bone_name])

	def test_fromClient_lang(self):
		from viur.core.bones import StringBone
		bone = StringBone(languages=["en", "de"])
		skel = {}
		lang = "de"
		data = {f"{self.bone_name}.{lang}": "foo"}
		self.assertIsNone(bone.fromClient(skel, self.bone_name, data))
		self.assertIn(self.bone_name, skel)
		self.assertIn(lang, skel[self.bone_name])
		self.assertIn("en", skel[self.bone_name])
		self.assertIsNone(skel[self.bone_name]["en"])
		self.assertNotIn("fr", skel[self.bone_name])
		self.assertEqual("foo", skel[self.bone_name][lang])

	def test_fromClient_multi_lang(self):
		from viur.core.bones import StringBone
		bone = StringBone(multiple=True, languages=["en", "de"])
		skel = {}
		lang = "de"
		data = {f"{self.bone_name}.{lang}": ["foo", "bar"]}
		self.assertIsNone(bone.fromClient(skel, self.bone_name, data))
		self.assertIn(self.bone_name, skel)
		self.assertIn(lang, skel[self.bone_name])
		self.assertEqual(["foo", "bar"], skel[self.bone_name][lang])
		self.assertIn("en", skel[self.bone_name])
		self.assertListEqual([], skel[self.bone_name]["en"])
		self.assertNotIn("fr", skel[self.bone_name])
