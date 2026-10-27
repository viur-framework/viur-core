import operator
from unittest import mock

from abstract import ViURTestCase


class FakeRelationsQuery:
    """In-memory stand-in for a ``viur-relations`` query, evaluating the ``viur_src_property`` filters."""

    OPERATORS = {"=": operator.eq, ">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}

    def __init__(self, store: dict):
        self.store = store
        self.filters = []

    def filter(self, prop: str, value):
        field, op = prop.split(" ")
        if field == "viur_src_property":
            self.filters.append((self.OPERATORS[op], value))
        return self

    def iter(self):
        return [
            entity for entity in list(self.store.values())
            if all(op(entity["viur_src_property"], value) for op, value in self.filters)
        ]

    run = iter


class TestRecordBonePostSavedHandler(ViURTestCase):
    """``RecordBone.postSavedHandler`` must only drop the ``viur-relations`` of removed record values."""

    # Relations of other bones of the same entity, sorting after the record bone "link"
    FOREIGN = ["link_other.00.element", "linkage", "page", "zzz"]

    def setUp(self) -> None:
        super().setUp()
        from viur.core import db
        from viur.core.bones import RelationalBone, StringBone
        from viur.core.skeleton import RelSkel

        class LinkSkel(RelSkel):
            element = RelationalBone(kind="element_kind")
            name = StringBone()
            page = RelationalBone(kind="page_kind")

        self.using = LinkSkel
        self.key = db.Key("src_kind", 1)

    def _bone(self, **kwargs):
        from viur.core.bones import RecordBone

        return RecordBone(using=self.using, format="$(name)", **kwargs)

    def _value(self) -> dict:
        """A record value; its sub-bones are mocks, so their own ``postSavedHandler`` doesn't hit the db."""
        return {name: mock.MagicMock(type=bone.type) for name, bone in self.using.__boneMap__.items()}

    def _save(self, bone, value, existing_paths: list[str]) -> list[str]:
        """
        Run ``postSavedHandler`` on stored relations and return the remaining ``viur_src_property`` paths.

        Deletions are applied regardless of whether they are done directly or by a deferred task.
        """
        from viur.core import db
        from viur.core.bones import record

        store = {}
        for path in existing_paths:
            entity = db.Entity(db.Key("viur-relations", path, parent=self.key))
            entity["viur_src_property"] = path
            store[entity.key] = entity

        def delete(keys):
            for key in keys if isinstance(keys, (list, set, tuple)) else [keys]:
                store.pop(key, None)

        def delete_iter(query):
            delete([entity.key for entity in query.iter()])

        skel = mock.MagicMock()
        skel.__getitem__.return_value = value

        patches = [
            mock.patch.object(record.db, "Query", side_effect=lambda kind: FakeRelationsQuery(store)),
            mock.patch.object(record.db, "delete", side_effect=delete),
        ]
        if hasattr(record, "tasks"):
            patches.append(mock.patch.object(record.tasks.DeleteEntitiesIter, "startIterOnQuery", delete_iter))

        for patch in patches:
            patch.start()
        try:
            bone.postSavedHandler(skel, "link", self.key)
        finally:
            for patch in patches:
                patch.stop()

        return sorted(entity["viur_src_property"] for entity in store.values())

    def test_shortened_list_drops_only_removed_values(self):
        existing = [
            "link.00.element", "link.00.page",
            "link.01.element", "link.01.page",
            "link.02.element", "link.02.page",
        ]

        remaining = self._save(self._bone(multiple=True), [self._value(), self._value()], existing + self.FOREIGN)

        self.assertEqual(remaining, sorted(existing[:4] + self.FOREIGN))

    def test_saved_siblings_are_kept(self):
        """Before, ``> "link.00.element"`` also matched the just written ``link.00.page``."""
        existing = ["link.00.element", "link.00.page"]

        remaining = self._save(self._bone(multiple=True), [self._value()], existing)

        self.assertEqual(remaining, existing)

    def test_other_bones_are_kept(self):
        """Before, the range had no upper bound and dropped relations of all bones sorting after this one."""
        remaining = self._save(self._bone(multiple=True), [self._value()], ["link.00.element"] + self.FOREIGN)

        self.assertEqual(remaining, sorted(["link.00.element"] + self.FOREIGN))

    def test_emptied_list_drops_all_values(self):
        existing = ["link.00.element", "link.00.page", "link.01.page"]

        remaining = self._save(self._bone(multiple=True), [], existing + self.FOREIGN)

        self.assertEqual(remaining, sorted(self.FOREIGN))

    def test_unknown_relations_are_kept(self):
        """Unknown sub-bones, nested containers and malformed paths may belong to another app version."""
        existing = [
            "link.00.element.00.page",  # nested record
            "link.01.name",  # not a relational sub-bone
            "link.01.removed_bone",
            "link.element",
            "link.xx.element",
        ]

        remaining = self._save(self._bone(multiple=True), [], existing)

        self.assertEqual(remaining, existing)

    def test_single_value(self):
        existing = ["link.00.element", "link.00.page"]

        remaining = self._save(self._bone(), self._value(), existing + self.FOREIGN)

        self.assertEqual(remaining, sorted(existing + self.FOREIGN))

    def test_languages(self):
        existing = ["link.de.00.element", "link.de.01.element", "link.en.00.page", "link.fr.00.element"]

        remaining = self._save(
            self._bone(multiple=True, languages=["de", "en"]),
            {"de": [self._value()], "en": []},
            existing,
        )

        # "fr" is not a configured language and stays
        self.assertEqual(remaining, ["link.de.00.element", "link.fr.00.element"])

    def test_truncated_values_skip_cleanup(self):
        existing = ["link.150.element"] + self.FOREIGN

        remaining = self._save(self._bone(multiple=True), [self._value() for _ in range(101)], existing)

        self.assertEqual(remaining, sorted(existing))

    def test_no_relational_sub_bones_skip_cleanup(self):
        from viur.core.bones import RecordBone, StringBone
        from viur.core.skeleton import RelSkel

        class TextSkel(RelSkel):
            name = StringBone()

        bone = RecordBone(using=TextSkel, format="$(name)", multiple=True)

        remaining = self._save(bone, [{"name": mock.MagicMock(type="str")}], ["link.00.name"] + self.FOREIGN)

        self.assertEqual(remaining, sorted(["link.00.name"] + self.FOREIGN))
