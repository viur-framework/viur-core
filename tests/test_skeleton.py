"""Tests for :class:`viur.core.skeleton.SkeletonInstance` and :meth:`Skeleton.write`."""
from unittest import mock

from abstract import ViURTestCase


def _translation_skel():
    from viur.core import bones, db  # noqa: F401  (import order, see project memory)
    from viur.core.modules.translation import TranslationSkel
    return TranslationSkel


class TestBoneMapModification(ViURTestCase):
    """``skel.bone = None`` removes a bone from the SkeletonInstance."""

    def test_assigning_none_removes_the_bone(self):
        skel = _translation_skel()()
        skel.hint = None
        self.assertNotIn("hint", skel)
        self.assertIn("default_text", skel)

    def test_reassigning_the_bone_takes_it_back(self):
        from viur.core.bones import StringBone
        skel = _translation_skel()()
        skel.hint = None
        skel.hint = StringBone(descr="hint")
        self.assertIn("hint", skel)

    def test_removal_survives_cloning(self):
        skel = _translation_skel()()
        skel.hint = None
        self.assertNotIn("hint", skel.clone())


class TestWriteRespectsBoneMap(ViURTestCase):
    """A bone removed from the skeleton must not be serialized by ``write()``."""

    def _write(self, skel, stored=None):
        """Run ``skel.write()`` against a mocked datastore.

        :param stored: The ``db.Entity`` the datastore already holds for the skeleton, if any.
        :return: The ``db.Entity`` that was written for the skeleton itself.
        """
        from viur.core import db
        from viur.core.skeleton import tasks

        written = []
        key = db.Key(skel.kindName, "test-entry")

        def get(db_key):
            """Only answer for the entity itself; unique- and blob-locks stay unclaimed."""
            if db_key.kind == skel.kindName:
                return stored
            return None

        with mock.patch.object(db, "allocate_ids", return_value=[key]), \
                mock.patch.object(db, "get", side_effect=get), \
                mock.patch.object(db, "put", side_effect=written.append), \
                mock.patch.object(db, "is_in_transaction", return_value=True), \
                mock.patch.object(tasks, "update_relations", mock.Mock()):
            skel.write()

        entities = [entity for entity in written if entity.key.kind == skel.kindName]
        self.assertEqual(1, len(entities))
        return entities[0]

    def test_removed_bone_is_not_written(self):
        skel = _translation_skel()()
        skel["name"] = "some.key"
        skel.hint = None
        entity = self._write(skel)
        self.assertNotIn("hint", entity)
        self.assertIn("default_text", entity)

    def test_removing_a_bone_keeps_the_values_of_the_others(self):
        skel = _translation_skel()()
        skel["name"] = "some.key"
        skel["default_text"] = "kept"
        skel.hint = None
        self.assertEqual("kept", self._write(skel)["default_text"])

    def test_removed_bone_keeps_the_value_already_stored(self):
        """Removing a bone excludes it from the write -- it does not clear the stored value."""
        from viur.core import db
        skel_cls = _translation_skel()
        stored = db.Entity(db.Key(skel_cls.kindName, "test-entry"))
        stored["name"] = "some.key"
        stored["hint"] = "kept"

        skel = skel_cls()
        skel.setEntity(stored)
        skel.hint = None
        entity = self._write(skel, stored=stored)
        self.assertEqual("kept", entity["hint"])

    def test_exactly_the_removed_bone_is_missing(self):
        """The bone map take-over must not drop anything but the bone that was removed."""
        skel_cls = _translation_skel()

        full = skel_cls()
        full["name"] = "some.key"

        reduced = skel_cls()
        reduced["name"] = "some.key"
        reduced.hint = None

        self.assertEqual(
            set(self._write(full).keys()) - {"hint"},
            set(self._write(reduced).keys()),
        )

    def test_removed_bone_keeps_its_blobs_locked(self):
        """Excluding a bone from the write must not release its blobs for deletion.

        The blob-lock is rebuilt from ``blob_list`` on every write: whatever is missing from
        it lands in ``old_blob_references``, and ``doCheckForUnreferencedBlobs`` marks those
        files for deletion -- while the entity still references them.
        """
        from viur.core import db
        from viur.core.bones import StringBone
        from viur.core.skeleton import tasks
        skel_cls = _translation_skel()

        stored = db.Entity(db.Key(skel_cls.kindName, "test-entry"))
        stored["name"] = "some.key"
        stored["hint"] = "references-a-blob"

        lock = db.Entity(db.Key("viur-blob-locks", "test-entry"))
        lock["active_blob_references"] = ["blob-1"]
        lock["old_blob_references"] = []
        lock["has_old_blob_references"] = False
        lock["is_stale"] = False

        def get(db_key):
            return {skel_cls.kindName: stored, "viur-blob-locks": lock}.get(db_key.kind)

        def referenced_blobs(self, skel, bone_name):
            return {"blob-1"} if bone_name == "hint" else set()

        skel = skel_cls()
        skel.setEntity(stored)
        skel["key"] = stored.key
        skel.hint = None

        with mock.patch.object(db, "get", side_effect=get), \
                mock.patch.object(db, "put", mock.Mock()), \
                mock.patch.object(db, "is_in_transaction", return_value=True), \
                mock.patch.object(StringBone, "getReferencedBlobs", referenced_blobs), \
                mock.patch.object(tasks, "update_relations", mock.Mock()):
            skel.write()

        self.assertEqual(["blob-1"], lock["active_blob_references"])
        self.assertEqual([], lock["old_blob_references"])

    def test_removed_bone_stays_in_the_search_index(self):
        """``ViurTagsSearchAdapter.prewrite`` replaces viurTags from the bones it sees.

        A bone excluded from the write keeps its stored value, so its search tags have to
        survive too -- otherwise editing through a skeleton that hides the bone makes the
        stored value unfindable.
        """
        from viur.core import db
        skel_cls = _translation_skel()

        stored = db.Entity(db.Key(skel_cls.kindName, "test-entry"))
        stored["name"] = "some.key"
        stored["translations"] = {"_viurLanguageWrapper_": True, "en": "searchable text"}

        skel = skel_cls()
        skel.setEntity(stored)
        skel["key"] = stored.key
        skel.translations = None
        self._write(skel, stored=stored)

        self.assertIn("searchable", stored["viurTags"])


_computed_skels = {}


def _computed_skel(method_name: str):
    """A skeleton with one bone computed by ``ComputeMethod.<method_name>``, plus ``label`` and ``payload`` that a
    ``preProcessSerializedData`` hook may change; defined once per process."""
    if method_name not in _computed_skels:
        import datetime
        from viur.core import conf, skeleton
        from viur.core.bones import Compute, ComputeInterval, ComputeMethod, NumericBone, RawBone, StringBone

        method = ComputeMethod[method_name]
        values = iter(range(1, 1000))

        # Skeletons must live in a folder listed in conf.skeleton_search_path; this one lives in the tests.
        with mock.patch.object(conf, "skeleton_search_path", [*conf.skeleton_search_path, "/"]):
            class ComputedSkel(skeleton.Skeleton):
                kindName = f"test-computed-{method_name.lower()}"
                hook = None  # set by a test: what preProcessSerializedData does to the entity

                label = StringBone()
                payload = RawBone()
                counter = NumericBone(compute=Compute(
                    fn=lambda skel: next(values),
                    interval=ComputeInterval(method, lifetime=datetime.timedelta(0)),
                ))

                @classmethod
                def preProcessSerializedData(cls, skel, entity):
                    if cls.hook is not None:
                        cls.hook(entity)
                    return entity

        _computed_skels[method_name] = ComputedSkel
    return _computed_skels[method_name]


_override_skel = []


def _shortkey_override_skel():
    """A skeleton defining its own ``shortkey``: computed ``Always`` like the base one, but not the base bone."""
    if not _override_skel:
        from viur.core import conf, skeleton
        from viur.core.bones import Compute, RawBone, StringBone

        with mock.patch.object(conf, "skeleton_search_path", [*conf.skeleton_search_path, "/"]):
            class ShortkeyOverrideSkel(skeleton.Skeleton):
                kindName = "test-shortkey-override"
                label = StringBone()
                shortkey = RawBone(compute=Compute(lambda skel: f"sk-{skel['label']}"))

        _override_skel.append(ShortkeyOverrideSkel)
    return _override_skel[0]


class _WriteWithFakeDb(ViURTestCase):
    """``Skeleton.write`` against a dict as datastore, with ``update_relations`` replaced by a mock."""

    def setUp(self):
        super().setUp()
        import copy
        import datetime
        from viur.core import db, utils
        from viur.core.skeleton import tasks

        self.docs = {}

        def get(key):
            return copy.deepcopy(self.docs.get((key.kind, key.id_or_name)))

        def put(entities):
            for entity in entities if isinstance(entities, list) else [entities]:
                self.docs[(entity.key.kind, entity.key.id_or_name)] = copy.deepcopy(entity)

        def allocate_ids(kind):
            return [db.Key(kind, "test-entry")]

        self.update_relations = mock.Mock()
        now = datetime.datetime(2026, 11, 14, tzinfo=datetime.timezone.utc)
        for patcher in (
            mock.patch.object(db, "get", side_effect=get),
            mock.patch.object(db, "put", side_effect=put),
            mock.patch.object(db, "allocate_ids", side_effect=allocate_ids),
            mock.patch.object(db, "is_in_transaction", return_value=True),
            mock.patch.object(tasks, "update_relations", self.update_relations),
            # changedate is computed on every write, at second resolution
            mock.patch.object(utils, "utcNow", return_value=now),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _add(self, skel_cls, **values):
        skel = skel_cls()
        for name, value in values.items():
            skel[name] = value
        self.key = skel.write()["key"]
        self.update_relations.assert_not_called()  # an add has nobody referencing it yet
        return self.key

    def _edit(self, skel_cls, **values):
        skel = skel_cls()
        self.assertTrue(skel.read(self.key))
        for name, value in values.items():
            skel[name] = value
        skel.write()


class TestWriteUpdatesRelationsOnChange(_WriteWithFakeDb):
    """An unchanged write leaves every stored bone as it was, so no entity mirroring it can be stale: it must not
    queue ``update_relations``, which without ``changed_bones`` refreshes every referencing entity."""

    def setUp(self):
        super().setUp()
        self.skel_cls = _translation_skel()
        self._add(self.skel_cls, name="some.key", default_text="old")

    def test_an_unchanged_write_queues_no_update(self):
        self._edit(self.skel_cls)
        self._edit(self.skel_cls, default_text="old")
        self.update_relations.assert_not_called()

    def test_a_changed_bone_queues_its_update(self):
        self._edit(self.skel_cls, default_text="new")
        self.update_relations.assert_called_once_with(self.key, changed_bones=["default_text"], _countdown=10)

    def test_a_changed_seo_key_queues_its_update(self):
        """``SeoKeyBone`` stores into ``viur.viurCurrentSeoKeys``, which the comparison per bone field missed."""
        stored = self.docs[(self.key.kind, self.key.id_or_name)]["viur"]["viurCurrentSeoKeys"]
        language = next(lang for lang in stored if not lang.startswith("_"))
        stored[language] = "a-key-the-write-replaces"
        self._edit(self.skel_cls)
        self.update_relations.assert_called_once_with(
            self.key, changed_bones=["viurCurrentSeoKeys"], _countdown=10)


class TestWriteUpdatesRelationsOutsideTheComparison(_WriteWithFakeDb):
    """Values that change without this write comparing them must still reach the referencing entities."""

    def _hooked_edit(self, hook, **values):
        skel_cls = _computed_skel("Once")  # computed once on add, unchanged afterwards
        self._add(skel_cls, **values)
        skel_cls.hook = staticmethod(hook)
        self.addCleanup(setattr, skel_cls, "hook", None)
        self._edit(skel_cls)

    def test_a_field_changed_by_a_hook_queues_its_update(self):
        self._hooked_edit(lambda entity: entity.update(label="hooked"), label="old")
        self.update_relations.assert_called_once_with(self.key, changed_bones=["label"], _countdown=10)

    def test_a_nested_value_changed_in_place_by_a_hook_queues_its_update(self):
        """``payload`` is not written by this edit; the hook changes its stored dict in place."""
        self._hooked_edit(lambda entity: entity["payload"].update(x="new"), payload={"x": "old"})
        self.update_relations.assert_called_once_with(self.key, changed_bones=["payload"], _countdown=10)

    def test_only_the_shortkey_of_skeleton_is_exempt(self):
        """The base ``shortkey`` is computed from the key alone and every relation mirrors it, so it does not count
        (the unchanged write above stays silent); a project's own ``shortkey`` is just another ``Always`` bone."""
        skel_cls = _shortkey_override_skel()
        self._add(skel_cls, label="same")
        self._edit(skel_cls)
        self.update_relations.assert_called_once_with(self.key, changed_bones=["shortkey"], _countdown=10)

    def test_a_bone_computed_on_read_always_counts_as_changed(self):
        """``Lifetime`` stores a recomputed value while reading and ``Always`` computes on every read: a write cannot
        tell whether that value moved, so the update always covers the entities mirroring it."""
        for method_name in ("Lifetime", "Always"):
            for values, changed in (({}, ["counter"]), ({"label": "new"}, ["label", "counter"])):
                with self.subTest(method_name, changed=changed):
                    skel_cls = _computed_skel(method_name)
                    self.update_relations.reset_mock()
                    self._add(skel_cls, label="same")
                    self._edit(skel_cls, **values)
                    self.update_relations.assert_called_once_with(self.key, changed_bones=changed, _countdown=10)


_many_always_skel = []


def _many_always_skel_cls():
    """A skeleton with four bones computed ``Always`` (besides the inherited ``shortkey``) and a plain ``label``."""
    if not _many_always_skel:
        from viur.core import conf, skeleton
        from viur.core.bones import Compute, ComputeInterval, ComputeMethod, RawBone, StringBone

        def always():
            return RawBone(compute=Compute(lambda skel: "constant", ComputeInterval(ComputeMethod.Always)))

        with mock.patch.object(conf, "skeleton_search_path", [*conf.skeleton_search_path, "/"]):
            class ManyAlwaysSkel(skeleton.Skeleton):
                kindName = "test-many-always"
                label = StringBone()
                c1, c2, c3, c4 = always(), always(), always(), always()

        _many_always_skel.append(ManyAlwaysSkel)
    return _many_always_skel[0]


class TestWriteWithManyComputedBones(_WriteWithFakeDb):
    """Bones computed ``Always`` count as changed on every write. They must not count towards the threshold of five
    that switches to the unfiltered update, which refreshes every referencing entity regardless of what it mirrors."""

    def test_one_changed_bone_keeps_the_filtered_update(self):
        skel_cls = _many_always_skel_cls()
        self._add(skel_cls, label="old")
        self._edit(skel_cls, label="new")
        args, kwargs = self.update_relations.call_args
        self.assertIn("changed_bones", kwargs, "one changed bone queued the unfiltered update_relations")


class TestWriteBeyondTheInFilterLimit(_WriteWithFakeDb):
    """The filtered ``update_relations`` queries ``viur_foreign_keys IN changed_bones``, and the datastore accepts at
    most 30 values there. Beyond that the task would fail on every attempt and nothing would be refreshed."""

    def test_more_than_30_changed_bones_queue_the_unfiltered_update(self):
        from viur.core import conf, skeleton
        from viur.core.bones import Compute, ComputeInterval, ComputeMethod, RawBone, StringBone

        with mock.patch.object(conf, "skeleton_search_path", [*conf.skeleton_search_path, "/"]):
            class ThirtyAlwaysSkel(skeleton.Skeleton):
                kindName = "test-thirty-always"
                label = StringBone()
                for _i in range(30):
                    vars()[f"c{_i}"] = RawBone(
                        compute=Compute(lambda skel: "constant", ComputeInterval(ComputeMethod.Always)))

        self._add(ThirtyAlwaysSkel, label="old")
        self._edit(ThirtyAlwaysSkel, label="new")  # changedate, label and 30 computed bones: 32 values
        self.update_relations.assert_called_once_with(self.key)
