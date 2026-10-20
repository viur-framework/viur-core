"""Tests for :func:`viur.core.skeleton.meta.relative_skeleton_path`."""
import pathlib
import unittest
from unittest import mock


class TestRelativeSkeletonPath(unittest.TestCase):
    """Core skeletons must resolve to ``/viur/core/...`` regardless of the working directory."""

    def _relative(self, filename: str, core_base_path: str, project_base_path: str) -> str:
        from viur.core import bones  # noqa: F401
        from viur.core import conf
        from viur.core.skeleton.meta import relative_skeleton_path

        with mock.patch.object(conf.instance, "core_base_path", pathlib.Path(core_base_path)), \
                mock.patch.object(conf.instance, "project_base_path", pathlib.Path(project_base_path)):
            return relative_skeleton_path(filename)

    def test_pypi_installation(self):
        self.assertEqual(
            "/viur/core/modules/user.py",
            self._relative(
                "/venv/lib/python3.13/site-packages/viur/core/modules/user.py",
                core_base_path="/venv/lib/python3.13/site-packages",
                project_base_path="/workspace",
            ),
        )

    def test_editable_installation_outside_of_the_project(self):
        self.assertEqual(
            "/viur/core/modules/user.py",
            self._relative(
                "/src/viur-core/src/viur/core/modules/user.py",
                core_base_path="/src/viur-core/src",
                project_base_path="/src/project/deploy",
            ),
        )

    def test_editable_installation_below_the_working_directory(self):
        """A submodule of the project, started from the project's root."""
        self.assertEqual(
            "/viur/core/modules/user.py",
            self._relative(
                "/project/viur-core/src/viur/core/modules/user.py",
                core_base_path="/project/viur-core/src",
                project_base_path="/project",
            ),
        )

    def test_test_suite_started_from_the_checkout(self):
        self.assertEqual(
            "/viur/core/modules/user.py",
            self._relative(
                "/viur-core/src/viur/core/modules/user.py",
                core_base_path="/viur-core/src",
                project_base_path="/viur-core",
            ),
        )

    def test_test_suite_started_from_the_parent_directory(self):
        """The layout of the GitHub workflow: checkout into ``viur/``, started from its parent."""
        self.assertEqual(
            "/viur/core/modules/user.py",
            self._relative(
                "/work/viur/src/viur/core/modules/user.py",
                core_base_path="/work/viur/src",
                project_base_path="/work",
            ),
        )

    def test_project_skeleton(self):
        self.assertEqual(
            "/skeletons/article.py",
            self._relative(
                "/workspace/skeletons/article.py",
                core_base_path="/venv/lib/python3.13/site-packages",
                project_base_path="/workspace",
            ),
        )

    def test_path_outside_of_core_and_project_is_unchanged(self):
        self.assertEqual(
            "/elsewhere/skeletons/article.py",
            self._relative(
                "/elsewhere/skeletons/article.py",
                core_base_path="/venv/lib/python3.13/site-packages",
                project_base_path="/workspace",
            ),
        )
