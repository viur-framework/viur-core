from unittest import mock

from abstract import ViURTestCase


class TestUidBoneInit(ViURTestCase):

    def _make(self, **kwargs):
        from viur.core.bones.uid import UidBone
        return UidBone(readOnly=True, **kwargs)

    def test_default_init(self):
        bone = self._make()
        self.assertEqual("*", bone.fillchar)
        self.assertEqual(13, bone.length)
        self.assertEqual("*", bone.pattern)

    def test_custom_pattern(self):
        bone = self._make(pattern="ORD-*")
        self.assertEqual("ORD-*", bone.pattern)

    def test_custom_fillchar(self):
        bone = self._make(fillchar="0")
        self.assertEqual("0", bone.fillchar)

    def test_custom_length(self):
        bone = self._make(length=8)
        self.assertEqual(8, bone.length)

    def test_multiple_raises(self):
        from viur.core.bones.uid import UidBone
        with self.assertRaises(ValueError):
            UidBone(readOnly=True, multiple=True)

    def test_not_readonly_raises(self):
        from viur.core.bones.uid import UidBone
        with self.assertRaises(ValueError):
            UidBone(readOnly=False)

    def test_pattern_without_wildcard_raises(self):
        from viur.core.bones.uid import UidBone
        with self.assertRaises(ValueError):
            UidBone(readOnly=True, pattern="NO-WILDCARD")

    def test_pattern_with_two_wildcards_raises(self):
        from viur.core.bones.uid import UidBone
        with self.assertRaises(ValueError):
            UidBone(readOnly=True, pattern="**")

    def test_fillchar_multiple_chars_raises(self):
        from viur.core.bones.uid import UidBone
        with self.assertRaises(ValueError):
            UidBone(readOnly=True, fillchar="00")

    def test_callable_pattern(self):
        bone = self._make(pattern=lambda: "INV-*")
        self.assertEqual("INV-*", bone.pattern)


class TestUidBoneStructure(ViURTestCase):

    def test_structure_keys(self):
        from viur.core.bones.uid import UidBone
        bone = UidBone(readOnly=True, pattern="INV-*", length=10, fillchar="0")
        s = bone.structure()
        self.assertEqual("INV-*", s["pattern"])
        self.assertEqual(10, s["length"])
        self.assertEqual("0", s["fillchar"])


class TestGenerateNumber(ViURTestCase):
    """The counter must not swallow datastore errors.

    ``generate_number`` used to wrap the increment in a retry loop catching a
    ``db.CollisionError`` that no longer exists. Evaluating that name replaced every real
    error with an ``AttributeError``, so the actual cause never reached the caller. A
    commit conflict is resolved by the surrounding ``db.run_in_transaction`` instead.
    """

    def _patched_db(self, entity=None, put_side_effect=None):
        from viur.core import db
        from viur.core.bones import uid
        stack = mock.patch.multiple(
            uid.db,
            get=mock.DEFAULT,
            put=mock.DEFAULT,
            is_in_transaction=mock.DEFAULT,
        )
        mocks = stack.start()
        self.addCleanup(stack.stop)
        mocks["get"].return_value = entity
        mocks["put"].side_effect = put_side_effect
        mocks["is_in_transaction"].return_value = True
        return db, mocks

    def test_first_call_starts_at_zero(self):
        from viur.core.bones.uid import generate_number
        db, mocks = self._patched_db(entity=None)
        with mock.patch.object(db, "Entity", lambda key: {}):
            self.assertEqual(0, generate_number(db.Key("viur-uids", "test")))
        mocks["put"].assert_called_once()

    def test_existing_counter_is_incremented(self):
        from viur.core.bones.uid import generate_number
        db, mocks = self._patched_db(entity={"count": 41})
        self.assertEqual(42, generate_number(db.Key("viur-uids", "test")))
        mocks["put"].assert_called_once_with({"count": 42})

    def test_datastore_error_propagates_unchanged(self):
        from viur.core.bones.uid import generate_number
        error = RuntimeError("datastore unavailable")
        db, _ = self._patched_db(entity={"count": 0}, put_side_effect=error)
        with self.assertRaises(RuntimeError) as ctx:
            generate_number(db.Key("viur-uids", "test"))
        self.assertIs(error, ctx.exception)
