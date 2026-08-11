"""
Tests for the user Status enum:
  Status is an IntEnum, so it must stay comparable with plain ints and with
  independently defined IntEnum classes (as projects do when they extend the
  status values in a subclassed UserSkel).
"""
import enum
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from abstract import ViURTestCase  # noqa: E402


class ProjectStatus(enum.IntEnum):
    """Stand-in for a project's own Status enum that mirrors the core values
    and adds a custom one — this is the pattern that used to break."""
    UNSET = 0
    WAITING_FOR_EMAIL_VERIFICATION = 1
    WAITING_FOR_ADMIN_VERIFICATION = 2
    DISABLED = 5
    ACTIVE = 10
    PENDING_REVIEW = 15


class TestUserStatus(ViURTestCase):

    def test_comparable_with_plain_int(self):
        from viur.core.modules.user import Status
        self.assertEqual(Status.ACTIVE, 10)
        self.assertTrue(Status.ACTIVE > 5)
        self.assertTrue(Status.DISABLED < Status.ACTIVE.value)

    def test_comparable_with_independent_project_enum(self):
        from viur.core.modules.user import Status
        self.assertEqual(Status.ACTIVE, ProjectStatus.ACTIVE)
        self.assertEqual(ProjectStatus.ACTIVE, Status.ACTIVE)
        self.assertTrue(Status.DISABLED < ProjectStatus.ACTIVE)
        self.assertTrue(ProjectStatus.PENDING_REVIEW > Status.ACTIVE)

    def test_not_always_truthy(self):
        # IntEnum follows int truthiness, unlike plain Enum members.
        from viur.core.modules.user import Status
        self.assertFalse(Status.UNSET)
        self.assertTrue(Status.ACTIVE)
