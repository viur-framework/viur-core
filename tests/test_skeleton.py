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
            if isinstance(key, list):  # like db.get: the entities found, missing ones left out
                return [entity for k in key if (entity := get(k)) is not None]
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

    def test_many_changed_bones_queue_the_full_update_after_the_same_delay(self):
        self._edit(self.skel_cls, default_text="new", hint="h", usage_filename="f.py", usage_lineno=1,
                   usage_variables=["v"])
        self.update_relations.assert_called_once_with(self.key, _countdown=10)

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


_relation_skels = []


def _relation_skel_classes():
    """A target with a ``name``, and a source mirroring it in a relation with ``updateLevel`` ``Always`` and in one with
    ``OnValueAssignment``."""
    if not _relation_skels:
        from viur.core import conf, skeleton
        from viur.core.bones import RelationalBone, RelationalUpdateLevel, StringBone

        class SideEffectBone(RelationalBone):
            """Like FileBone, whose refresh patches file entries: such extras must not run inside write."""
            calls = []

            def refresh(self, skel, name):
                self.calls.append(name)
                super().refresh(skel, name)

        with mock.patch.object(conf, "skeleton_search_path", [*conf.skeleton_search_path, "/"]):
            class RelTargetSkel(skeleton.Skeleton):
                kindName = "test-rel-target"
                name = StringBone()

            class RelSourceSkel(skeleton.Skeleton):
                kindName = "test-rel-source"
                rel = RelationalBone(kind="test-rel-target", module="test", refKeys=["name"])
                rel_assign = RelationalBone(kind="test-rel-target", module="test", refKeys=["name"],
                                            updateLevel=RelationalUpdateLevel.OnValueAssignment)
                rel_extra = SideEffectBone(kind="test-rel-target", module="test", refKeys=["name"])

        for cls in (RelTargetSkel, RelSourceSkel):
            cls.setSystemInitialized()  # what viur.core.setup() does: builds the reference skeletons of relations
        _relation_skels.extend((RelTargetSkel, RelSourceSkel))
    return _relation_skels


class TestWriteRefreshesRelationCopies(_WriteWithFakeDb):
    """A relation value is loaded when it is assigned (``fromClient``, ``setBoneValue``) and written later. If its
    target is renamed in between and its ``update_relations`` already refreshed this entity, writing the copy loaded
    before would put the old name back for good. ``write`` reads the targets again inside its transaction."""

    def setUp(self):
        super().setUp()
        from viur.core.bones import RelationalBone
        for name in ("postSavedHandler", "postDeletedHandler"):  # maintain viur-relations, needs queries
            patcher = mock.patch.object(RelationalBone, name, return_value=None)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.target_cls, self.source_cls = _relation_skel_classes()
        self.target_key = self._add(self.target_cls, name="old")

    def _source_with_copies_of(self):
        skel = self.source_cls()
        skel.setBoneValue("rel", self.target_key)
        skel.setBoneValue("rel_assign", self.target_key)
        skel.setBoneValue("rel_extra", self.target_key)
        return skel

    def _rename_target(self, name):
        self.docs[(self.target_key.kind, self.target_key.id_or_name)]["name"] = name

    def _stored(self, key):
        return self.docs[(key.kind, key.id_or_name)]

    def test_copy_loaded_before_a_rename_is_written_fresh(self):
        skel = self._source_with_copies_of()
        self._rename_target("new")  # committed while the edit was still running (a slow hook, a long form)
        key = skel.write()["key"]
        self.assertEqual(self._stored(key)["rel"]["dest"]["name"], "new")

    def test_on_value_assignment_keeps_the_assigned_copy(self):
        skel = self._source_with_copies_of()
        self._rename_target("new")
        key = skel.write()["key"]
        self.assertEqual(self._stored(key)["rel_assign"]["dest"]["name"], "old")

    def test_subclass_extras_of_refresh_do_not_run(self):
        skel = self._source_with_copies_of()
        bone = self.source_cls.rel_extra
        bone.calls.clear()
        self._rename_target("new")
        key = skel.write()["key"]
        self.assertEqual(bone.calls, [])
        self.assertEqual(self._stored(key)["rel_extra"]["dest"]["name"], "new")  # the copy itself is refreshed


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
        self.update_relations.assert_called_once_with(self.key, _countdown=10)


_matrix_skels = []


def _matrix_skel_classes():
    """A target, and a source holding it in every shape a relation can take."""
    if not _matrix_skels:
        from viur.core import conf, skeleton
        from viur.core.bones import (
            RecordBone, RelationalBone, RelationalConsistency, RelationalUpdateLevel, StringBone,
        )
        from viur.core.skeleton import RelSkel

        def rel(**kwargs):
            return RelationalBone(kind="test-matrix-target", module="test", refKeys=["name"], **kwargs)

        with mock.patch.object(conf, "skeleton_search_path", [*conf.skeleton_search_path, "/"]):
            class MatrixTargetSkel(skeleton.Skeleton):
                kindName = "test-matrix-target"
                name = StringBone()

            class MatrixInner(RelSkel):
                inner = rel()
                inner_assign = rel(updateLevel=RelationalUpdateLevel.OnValueAssignment)

            class MatrixOuter(RelSkel):
                deep = RecordBone(using=MatrixInner, multiple=True, format="$(name)")

            class MatrixSourceSkel(skeleton.Skeleton):
                kindName = "test-matrix-source"
                label = StringBone()
                single = rel()
                multi = rel(multiple=True)
                lang = rel(languages=["de", "en"])
                multi_lang = rel(multiple=True, languages=["de", "en"])
                using = rel(using=MatrixInner)
                multi_using = rel(using=MatrixInner, multiple=True)
                record = RecordBone(using=MatrixInner, format="$(name)")
                records = RecordBone(using=MatrixInner, multiple=True, format="$(name)")
                nested = RecordBone(using=MatrixOuter, multiple=True, format="$(name)")
                assign = rel(updateLevel=RelationalUpdateLevel.OnValueAssignment)
                rebuild = rel(updateLevel=RelationalUpdateLevel.OnRebuildSearchIndex)
                own_kind = RelationalBone(kind="test-matrix-source", module="test", refKeys=["label"])
                cascade = rel(consistency=RelationalConsistency.CascadeDeletion)
                set_null = rel(consistency=RelationalConsistency.SetNull)

        for cls in (MatrixTargetSkel, MatrixSourceSkel, MatrixInner, MatrixOuter):
            cls.setSystemInitialized()  # as viur.core.setup() does for every skeleton class, RelSkels included
        _matrix_skels.extend((MatrixTargetSkel, MatrixSourceSkel, MatrixInner, MatrixOuter))
    return _matrix_skels


def _stored_copies(value, path=()):
    """(path, mirrored value) of every relation copy inside a stored entity, at any depth."""
    if isinstance(value, dict):
        if "dest" in value and isinstance(value["dest"], dict):
            dest = value["dest"]
            yield ".".join(map(str, path)), dest.get("name", dest.get("label"))
            yield from _stored_copies(value.get("rel"), (*path, "rel"))
        else:
            for name, item in value.items():
                yield from _stored_copies(item, (*path, name))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _stored_copies(item, (*path, index))


class TestWriteRefreshesEveryShapeOfRelation(_WriteWithFakeDb):
    """Whatever shape a relation has (single, multiple, per language, with a ``using`` skeleton, inside records, inside
    records of records, to its own kind): a copy loaded before its target changed is written with the target's
    current values. Copies that are frozen on purpose (``OnValueAssignment``, ``OnRebuildSearchIndex``) stay."""

    FROZEN = ("assign", "rebuild", "inner_assign")

    def setUp(self):
        super().setUp()
        from viur.core.bones import RecordBone, RelationalBone
        for bone_cls in (RelationalBone, RecordBone):
            for name in ("postSavedHandler", "postDeletedHandler"):  # maintain viur-relations, needs queries
                patcher = mock.patch.object(bone_cls, name, return_value=None)
                patcher.start()
                self.addCleanup(patcher.stop)
        self.target_cls, self.source_cls, self.inner_cls, self.outer_cls = _matrix_skel_classes()
        self.target_key = self._add(self.target_cls, name="old")
        other = self.source_cls()
        other["label"] = "old"
        other["key"] = self.other_key = __import__("viur.core.db", fromlist=["Key"]).Key("test-matrix-source", "other")
        other.write()

    def _inner(self):
        inner = self.inner_cls()
        inner.setBoneValue("inner", self.target_key)
        inner.setBoneValue("inner_assign", self.target_key)
        return inner

    def _source(self):
        skel = self.source_cls()
        for name in ("single", "assign", "rebuild", "cascade", "set_null"):
            self.assertTrue(skel.setBoneValue(name, self.target_key), name)
        for _ in range(2):  # the same target twice
            self.assertTrue(skel.setBoneValue("multi", self.target_key, append=True))
            self.assertTrue(skel.setBoneValue("multi_using", (self.target_key, self._inner()), append=True))
        for language in ("de", "en"):
            self.assertTrue(skel.setBoneValue("lang", self.target_key, language=language))
            self.assertTrue(skel.setBoneValue("multi_lang", self.target_key, append=True, language=language))
        self.assertTrue(skel.setBoneValue("using", (self.target_key, self._inner())))
        self.assertTrue(skel.setBoneValue("own_kind", self.other_key))
        skel["record"] = self._inner()
        skel["records"] = [self._inner(), self._inner()]
        outer = self.outer_cls()
        outer["deep"] = [self._inner()]
        skel["nested"] = [outer]
        return skel

    def _copies_after_rename(self, skel):
        self.docs[(self.target_key.kind, self.target_key.id_or_name)]["name"] = "new"
        self.docs[(self.other_key.kind, self.other_key.id_or_name)]["label"] = "new"
        key = skel.write()["key"]
        return dict(_stored_copies(self.docs[(key.kind, key.id_or_name)]))

    def test_every_copy_is_written_fresh(self):
        copies = self._copies_after_rename(self._source())
        self.assertEqual(len(copies), 29, copies)  # the matrix really reached the stored entity
        for path, value in copies.items():
            frozen = any(part in self.FROZEN for part in path.split("."))
            with self.subTest(path=path):
                self.assertEqual(value, "old" if frozen else "new")

    def test_a_read_and_rewritten_entity_is_written_fresh(self):
        key = self._source().write()["key"]  # stored with the old name everywhere
        skel = self.source_cls()
        self.assertTrue(skel.read(key))
        for name in skel:  # as a form does: every bone is read, then written back
            _ = skel[name]
        copies = self._copies_after_rename(skel)
        for path, value in copies.items():
            frozen = any(part in self.FROZEN for part in path.split("."))
            with self.subTest(path=path):
                self.assertEqual(value, "old" if frozen else "new")

    def test_deleted_target_is_left_alone(self):
        # refresh() would empty a SetNull relation and flag a CascadeDeletion one in the middle of this write.
        # Handling a deleted target is up to its deletion and to refresh(), not to a write of the source.
        skel = self._source()
        del self.docs[(self.target_key.kind, self.target_key.id_or_name)]
        key = skel.write()["key"]
        stored = self.docs[(key.kind, key.id_or_name)]
        for name in ("single", "cascade", "set_null"):
            self.assertEqual(stored[name]["dest"]["name"], "old", name)
