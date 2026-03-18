"""Regression tests for RecordBone None-value handling.

When iter_bone_value yields None entries (e.g. from corrupt or partial data),
postSavedHandler, postDeletedHandler, and refresh must skip them gracefully
instead of raising ``AttributeError: 'NoneType' object has no attribute 'items'``.

See: https://github.com/viur-framework/viur-core/pull/1652
"""
import pytest
from unittest.mock import MagicMock


BONE_NAME = "myRecord"


def _make_bone(multiple=True):
    from viur.core.bones import StringBone
    from viur.core.bones.record import RecordBone
    from viur.core.skeleton.relskel import RelSkel

    class _Rel(RelSkel):
        name = StringBone(descr="Name")

    return RecordBone(using=_Rel, format="$(name)", multiple=multiple)


class TestRecordBoneNoneGuard:
    """RecordBone iteration methods must not crash on None values."""

    # -- Only None values (pure regression) ----------------------------------

    def test_postSavedHandler_skips_none(self):
        """postSavedHandler must not raise when value list contains None."""
        bone = _make_bone()
        skel = {BONE_NAME: [None]}
        bone.postSavedHandler(skel, BONE_NAME, MagicMock())

    def test_postDeletedHandler_skips_none(self):
        """postDeletedHandler must not raise when value list contains None."""
        bone = _make_bone()
        skel = {BONE_NAME: [None]}
        bone.postDeletedHandler(skel, BONE_NAME, MagicMock())

    def test_refresh_skips_none(self):
        """refresh must not raise when value list contains None."""
        bone = _make_bone()
        skel = {BONE_NAME: [None]}
        bone.refresh(skel, BONE_NAME)

    # -- None mixed with valid values ----------------------------------------

    def test_postSavedHandler_skips_none_among_valid(self):
        """None values are skipped while valid SkeletonInstances are processed."""
        bone = _make_bone()
        valid = bone.using()
        valid.unserialize({"name": "test"})
        skel = {BONE_NAME: [None, valid, None]}
        bone.postSavedHandler(skel, BONE_NAME, MagicMock())

    def test_postDeletedHandler_skips_none_among_valid(self):
        """None values are skipped while valid SkeletonInstances are processed."""
        bone = _make_bone()
        valid = bone.using()
        valid.unserialize({"name": "test"})
        skel = {BONE_NAME: [None, valid, None]}
        bone.postDeletedHandler(skel, BONE_NAME, MagicMock())

    def test_refresh_skips_none_among_valid(self):
        """None values are skipped while valid SkeletonInstances are processed."""
        bone = _make_bone()
        valid = bone.using()
        valid.unserialize({"name": "test"})
        skel = {BONE_NAME: [None, valid, None]}
        bone.refresh(skel, BONE_NAME)

    # -- Multiple None values ------------------------------------------------

    def test_postSavedHandler_all_none(self):
        """An entirely None-filled list must not crash."""
        bone = _make_bone()
        skel = {BONE_NAME: [None, None, None]}
        bone.postSavedHandler(skel, BONE_NAME, MagicMock())

    def test_postDeletedHandler_all_none(self):
        """An entirely None-filled list must not crash."""
        bone = _make_bone()
        skel = {BONE_NAME: [None, None, None]}
        bone.postDeletedHandler(skel, BONE_NAME, MagicMock())

    def test_refresh_all_none(self):
        """An entirely None-filled list must not crash."""
        bone = _make_bone()
        skel = {BONE_NAME: [None, None, None]}
        bone.refresh(skel, BONE_NAME)
