from unittest import mock

from abstract import ViURTestCase


def _bone():
    from viur.core.bones import RecordBone
    from viur.core.skeleton import RelSkel

    class _Using(RelSkel):
        pass

    return RecordBone(using=_Using, format="$(name)", multiple=True)


class TestRecordBoneWritePathNoneValues(ViURTestCase):
    """A stored ``null`` inside a ``multiple`` record must not break save or delete.

    ``getSearchTags`` and ``getReferencedBlobs`` guard the same loop with
    ``if value is None: continue``; the write path did not and raised an AttributeError.
    """

    def _skel_and_key(self):
        from viur.core import db
        return mock.MagicMock(), db.Key("test", "1")

    def _iter_values(self, bone, values):
        """Make ``iter_bone_value`` yield the given values, as the datastore would."""
        return mock.patch.object(
            bone, "iter_bone_value",
            return_value=iter([(idx, None, value) for idx, value in enumerate(values)]),
        )

    def test_postSavedHandler_skips_none(self):
        bone = _bone()
        skel, key = self._skel_and_key()
        with self._iter_values(bone, [None]):
            bone.postSavedHandler(skel, "records", key)

    def test_postDeletedHandler_skips_none(self):
        bone = _bone()
        skel, key = self._skel_and_key()
        with self._iter_values(bone, [None]):
            bone.postDeletedHandler(skel, "records", key)

    def test_postSavedHandler_still_processes_entries_after_none(self):
        bone = _bone()
        skel, key = self._skel_and_key()
        sub_bone = mock.MagicMock()
        sub_bone.type = "string"
        entry = {"name": sub_bone}
        with self._iter_values(bone, [None, entry]):
            bone.postSavedHandler(skel, "records", key)
        sub_bone.postSavedHandler.assert_called_once_with(entry, "records.01.name", key)

    def test_postDeletedHandler_still_processes_entries_after_none(self):
        bone = _bone()
        skel, key = self._skel_and_key()
        sub_bone = mock.MagicMock()
        sub_bone.type = "string"
        entry = {"name": sub_bone}
        with self._iter_values(bone, [None, entry]):
            bone.postDeletedHandler(skel, "records", key)
        sub_bone.postDeletedHandler.assert_called_once_with(entry, "records.01.name", key)
