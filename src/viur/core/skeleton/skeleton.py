from __future__ import annotations  # noqa: required for pre-defined annotations

import logging
import time
import typing as t
import warnings

from deprecated.sphinx import deprecated

from viur.core import conf, db, errors, utils
from . import tasks
from .base import BaseSkeleton
from .meta import MetaSkel, _UNDEFINED_KINDNAME
from .utils import skeletonByKind
from ..bones.base import (
    Compute,
    ComputeInterval,
    ComputeMethod,
    ReadFromClientError,
    ReadFromClientErrorSeverity,
    ReadFromClientException,
)
from ..bones.date import DateBone
from ..bones.key import KeyBone
from ..bones.relational import RelationalConsistency
from ..bones.string import StringBone

if t.TYPE_CHECKING:
    from .instance import SkeletonInstance
    from .adapter import DatabaseAdapter


def _check_key(key: t.Any) -> str:
    """Validate an ``_id`` for the skeleton read and write path.

    An ``_id`` carries no kind that could be checked or adjusted, so this is the plain type
    check that ``db.get``, ``db.put`` and ``db.delete`` enforce anyway.

    :raises ValueError: if *key* is not a non-empty ``str``.
    """
    if not (isinstance(key, str) and key):
        raise ValueError(f"{key!r} is not a valid key")
    return key


class SeoKeyBone(StringBone):
    """
    Special kind of StringBone saving its contents as `viurCurrentSeoKeys` into the entity's `viur` dict.
    """

    def setSystemInitialized(self):
        super().setSystemInitialized()
        self.languages = conf.i18n.available_languages

    def unserialize(self, skel: SkeletonInstance, name: str) -> bool:
        try:
            skel.accessedValues[name] = skel.dbEntity["viur"]["viurCurrentSeoKeys"]
        except KeyError:
            skel.accessedValues[name] = self.getDefaultValue(skel)

    def serialize(self, skel: SkeletonInstance, name: str, parentIndexed: bool) -> bool:
        # Serialize also to skel["viur"]["viurCurrentSeoKeys"], so we can use this bone in relations
        if name in skel.accessedValues:
            newVal = skel.accessedValues[name]
            if not skel.dbEntity.get("viur"):
                skel.dbEntity["viur"] = {}
            res = {"_viurLanguageWrapper_": True}
            for language in (self.languages or []):
                # MongoDB has no per-field index exclusion; every field is queryable.
                res[language] = None
                if language in newVal:
                    res[language] = self.singleValueSerialize(newVal[language], skel, name, parentIndexed)
            skel.dbEntity["viur"]["viurCurrentSeoKeys"] = res
        return True


class Skeleton(BaseSkeleton, metaclass=MetaSkel):
    kindName: str = _UNDEFINED_KINDNAME
    """
    Specifies the entity kind name this Skeleton is associated with.
    Will be determined automatically when not explicitly set.
    """

    database_adapters: DatabaseAdapter | t.Iterable[DatabaseAdapter] | None = _UNDEFINED_KINDNAME
    """
    Custom database adapters.
    Allows to hook special functionalities that during skeleton modifications.
    """

    subSkels = {}  # List of pre-defined sub-skeletons of this type

    interBoneValidations: list[
        t.Callable[[Skeleton], list[ReadFromClientError]]] = []  # List of functions checking inter-bone dependencies

    __seo_key_trans = str.maketrans(
        {"<": "",
         ">": "",
         "\"": "",
         "'": "",
         "\n": "",
         "\0": "",
         "/": "",
         "\\": "",
         "?": "",
         "&": "",
         "#": ""
         })

    # The "key" bone stores the current database key of this skeleton.
    # Warning: Assigning to this bones value now *will* set the key
    # it gets stored in. Must be kept readOnly to avoid security-issues with add/edit.
    key = KeyBone(
        descr="Key"
    )

    # There is no "shortkey" bone: an `_id` is already a short reference that is unique on
    # its own.

    name = StringBone(
        descr="Name",
        visible=False,
        compute=Compute(
            fn=lambda skel: f"{skel.kindName}/{skel["key"]}" if skel["key"] else None,
            interval=ComputeInterval(ComputeMethod.OnWrite)
        )
    )

    # The date (including time) when this entry has been created
    creationdate = DateBone(
        descr="created at",
        readOnly=True,
        visible=False,
        indexed=True,
        compute=Compute(
            lambda: utils.utcNow().replace(microsecond=0),
            interval=ComputeInterval(ComputeMethod.Once)
        ),
        tags="technical",
    )

    # The last date (including time) when this entry has been updated

    changedate = DateBone(
        descr="updated at",
        readOnly=True,
        visible=False,
        indexed=True,
        compute=Compute(
            lambda: utils.utcNow().replace(microsecond=0),
            interval=ComputeInterval(ComputeMethod.OnWrite)
        ),
        tags="technical",
    )

    viurCurrentSeoKeys = SeoKeyBone(
        descr="SEO-Keys",
        readOnly=True,
        visible=False,
        languages=conf.i18n.available_languages,
    )

    def __repr__(self):
        return "<skeleton %s with data=%r>" % (self.kindName, {k: self[k] for k in self.keys()})

    def __str__(self):
        return str({k: self[k] for k in self.keys()})

    def __init__(self, *args, **kwargs):
        super(Skeleton, self).__init__(*args, **kwargs)
        assert self.kindName and self.kindName is not _UNDEFINED_KINDNAME, "You must set kindName on this skeleton!"

    @classmethod
    def all(cls, skel, **kwargs) -> db.Query:
        """
            Create a query with the current Skeletons kindName.

            :returns: A db.Query object which allows for entity filtering and sorting.
        """
        return db.Query(skel.kindName, srcSkelClass=skel, **kwargs)

    @classmethod
    def fromClient(
        cls,
        skel: "SkeletonInstance[t.Self]",
        data: dict[str, list[str] | str],
        *,
        amend: bool = False,
        ignore: t.Optional[t.Iterable[str]] = None,
    ) -> bool:
        """
            This function works similar to :func:`~viur.core.skeleton.Skeleton.setValues`, except that
            the values retrieved from *data* are checked against the bones and their validity checks.

            Even if this function returns False, all bones are guaranteed to be in a valid state.
            The ones which have been read correctly are set to their valid values;
            Bones with invalid values are set back to a safe default (None in most cases).
            So its possible to call :func:`~viur.core.skeleton.Skeleton.write` afterwards even if reading
            data with this function failed (through this might violates the assumed consistency-model).

            :param skel: The skeleton instance to be filled.
            :param data: Dictionary from which the data is read.
            :param amend: Defines whether content of data may be incomplete to amend the skel,
                which is useful for edit-actions.
            :param ignore: optional list of bones to be ignored; Defaults to all readonly-bones when set to None.

            :returns: True if all data was successfully read and complete. \
            False otherwise (e.g. some required fields where missing or where invalid).
        """
        assert skel.renderPreparation is None, "Cannot modify values while rendering"

        # Load data into this skeleton
        complete = bool(data) and super().fromClient(skel, data, amend=amend, ignore=ignore)

        if (
            not data  # in case data is empty
            or (len(data) == 1 and "key" in data)
            or (utils.parse.bool(data.get("nomissing")))
        ):
            skel.errors = []

        # Check if all unique values are available
        for boneName, boneInstance in skel.items():
            if boneInstance.unique:
                lockValues = boneInstance.getUniquePropertyIndexValues(skel, boneName)

                for lockValue in lockValues:
                    lock_kind = f"{skel.kindName}_{boneName}_uniquePropertyIndex"
                    lock_entity = db.get(lock_kind, lockValue)

                    if lock_entity and (not skel["key"] or lock_entity["references"] != skel["key"]):
                        logging.error(f"{boneName=} {lock_kind=} {lockValue=} already taken "
                                      f"by {lock_entity["references"]!r}")

                        # This value is taken (sadly, not by us)
                        complete = False
                        skel.errors.append(
                            ReadFromClientError(
                                ReadFromClientErrorSeverity.Invalid,
                                boneInstance.unique.message,
                                [boneName]
                            )
                        )

        # Check inter-Bone dependencies
        for checkFunc in skel.interBoneValidations:
            errors = checkFunc(skel)
            if errors:
                for error in errors:
                    if error.severity.value > 1:
                        complete = False
                        if conf.debug.skeleton_from_client:
                            logging.debug(f"{cls.kindName}: {error.fieldPath}: {error.errorMessage!r}")

                skel.errors.extend(errors)

        return complete

    @classmethod
    @deprecated(
        version="3.7.0",
        reason="Use skel.read() instead of skel.fromDB()",
    )
    def fromDB(cls, skel: SkeletonInstance, key: str) -> bool:
        """
        Deprecated function, replaced by Skeleton.read().
        """
        return bool(cls.read(skel, key, _check_legacy=False))

    @classmethod
    def read(
        cls,
        skel: SkeletonInstance,
        key: str | None = None,
        *,
        create: bool | dict | t.Callable[[SkeletonInstance], None] = False,
        _check_legacy: bool = True
    ) -> t.Optional[SkeletonInstance]:
        """
            Read Skeleton with *key* from the datastore into the Skeleton.
            If not key is given, skel["key"] will be used.

            Reads all available data of entity kind *kindName* and the key *key*
            from the Datastore into the Skeleton structure's bones. Any previous
            data of the bones will discard.

            To store a Skeleton object to the Datastore, see :func:`~viur.core.skeleton.Skeleton.write`.

            :param key: The ``_id`` string from which the data shall be fetched.
                If not provided, skel["key"] will be used.
            :param create: Allows to specify a dict or initial callable that is executed in case the Skeleton with the
                given key does not exist, it will be created.

            :returns: None on error, or the given SkeletonInstance on success.

        """
        # FIXME VIUR4: Stay backward compatible, call sub-classed fromDB if available first!
        if _check_legacy and "fromDB" in cls.__dict__:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                return cls.fromDB(skel, key=key)

        assert skel.renderPreparation is None, "Cannot modify values while rendering"

        try:
            db_key = _check_key(key or skel["key"])
        except ValueError:  # This key did not parse
            return None

        if db_res := db.get(skel.kindName, db_key):
            skel.setEntity(db_res)
            return skel
        elif create in (False, None):
            return None
        elif isinstance(create, dict):
            if create and not skel.fromClient(create, amend=True, ignore=()):
                raise ReadFromClientException(skel.errors)
        elif callable(create):
            create(skel)
        elif create is not True:
            raise ValueError("'create' must either be dict, a callable or True.")

        skel["key"] = db_key
        return skel.write()

    @classmethod
    @deprecated(
        version="3.7.0",
        reason="Use skel.write() instead of skel.toDB()",
    )
    def toDB(cls, skel: SkeletonInstance, update_relations: bool = True, **kwargs) -> str:
        """
        Deprecated function, replaced by Skeleton.write().
        """

        # TODO: Remove with ViUR4
        if "clearUpdateTag" in kwargs:
            msg = "clearUpdateTag was replaced by update_relations"
            warnings.warn(msg, DeprecationWarning, stacklevel=3)
            logging.warning(msg, stacklevel=3)
            update_relations = not kwargs["clearUpdateTag"]

        skel = cls.write(skel, update_relations=update_relations, _check_legacy=False)
        return skel["key"]

    @classmethod
    def write(
        cls,
        skel: SkeletonInstance,
        key: str | None = None,
        *,
        update_relations: bool = True,
        _check_legacy: bool = True,
    ) -> SkeletonInstance:
        """
            Write current Skeleton to the datastore.

            Stores the current data of this instance into the database.
            If an *key* value is set to the object, this entity will ne updated;
            Otherwise a new entity will be created.

            To read a Skeleton object from the data store, see :func:`~viur.core.skeleton.Skeleton.read`.

            :param key: Allows to specify a key that is set to the skeleton and used for writing.
            :param update_relations: If False, this entity won't be marked dirty;
                This avoids from being fetched by the background task updating relations.

            :returns: The Skeleton.
        """
        # FIXME VIUR4: Stay backward compatible, call sub-classed toDB if available first!
        if _check_legacy and "toDB" in cls.__dict__:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                return cls.toDB(skel, update_relations=update_relations)

        # FIXME: This check is incomplete as long it does nt check the entire tree!
        assert skel.renderPreparation is None, "Cannot modify values while rendering"

        def __txn_write(write_skel):
            db_key = write_skel["key"]
            skel = write_skel.skeletonCls()

            blob_list = set()
            change_list = []
            old_copy = {}
            # Load the current values from Datastore or create a new, empty document.
            if not db_key:
                skel.dbEntity = {}
                is_add = True
            else:
                db_key = _check_key(db_key)
                if db_obj := db.get(skel.kindName, db_key):
                    skel.dbEntity = db_obj
                    old_copy = {k: v for k, v in skel.dbEntity.items()}
                    is_add = False
                else:
                    skel.dbEntity = {"_id": db_key}
                    is_add = True

            skel.dbEntity.setdefault("viur", {})

            # The unique- and blob-locks below refer to `skel["key"]` and need it *before* the
            # entity itself is written, while `db.put()` only fills in a missing `_id` when it
            # is actually called at the very end of this function. Therefore the id is created
            # upfront and written into the not-yet-persisted document, which avoids a second
            # `put()` with two roundtrips and two entities to keep in sync.
            db_key = skel.dbEntity.setdefault("_id", db.objectid.new_id())

            # Merge values and assemble unique properties
            # Move accessed Values from srcSkel over to skel
            skel.accessedValues = write_skel.accessedValues

            write_skel["key"] = skel["key"] = db_key  # Ensure key stays set
            write_skel.dbEntity = skel.dbEntity  # update write_skel's dbEntity

            for bone_name, bone in skel.items():
                if bone_name == "key":  # Explicitly skip key on top-level - this had been set above
                    continue

                if bone_name not in write_skel.boneMap:
                    # The bone is not part of write_skel: it was either removed from it with
                    # `skel.bone = None`, or it never was part of it (a subskel). Don't serialize
                    # it, so that whatever is stored for it stays untouched. Its blobs are still
                    # collected, otherwise the blob-lock below would release them for deletion.
                    blob_list.update(bone.getReferencedBlobs(skel, bone_name))
                    continue

                # Allow bones to perform outstanding "magic" operations before saving to db
                bone.performMagic(skel, bone_name, isAdd=is_add)  # FIXME VIUR4: ANY MAGIC IN OUR CODE IS DEPRECATED!!!

                if not (bone_name in skel.accessedValues or bone.compute) and bone_name not in skel.dbEntity:
                    _ = skel[bone_name]  # Ensure the datastore is filled with the default value

                if (
                    bone_name in skel.accessedValues or bone.compute  # We can have a computed value on store
                    or bone_name not in skel.dbEntity  # It has not been written and is not in the database
                ):
                    # Serialize bone into entity
                    try:
                        bone.serialize(skel, bone_name, True)
                    except Exception as e:
                        logging.error(
                            f"Failed to serialize {bone_name=} ({bone=}): {skel.accessedValues[bone_name]=}"
                        )
                        raise e

                # Obtain referenced blobs
                blob_list.update(bone.getReferencedBlobs(skel, bone_name))

                # Check if the value has actually changed
                if skel.dbEntity.get(bone_name) != old_copy.get(bone_name):
                    change_list.append(bone_name)

                # Lock hashes from bones that must have unique values
                if bone.unique:
                    # Remember old hashes for bones that must have an unique value
                    old_unique_values = []

                    if f"{bone_name}_uniqueIndexValue" in skel.dbEntity["viur"]:
                        old_unique_values = skel.dbEntity["viur"][f"{bone_name}_uniqueIndexValue"]
                    # Check if the property is unique
                    new_unique_values = bone.getUniquePropertyIndexValues(skel, bone_name)
                    new_lock_kind = f"{skel.kindName}_{bone_name}_uniquePropertyIndex"
                    for new_lock_value in new_unique_values:
                        if lock_db_obj := db.get(new_lock_kind, new_lock_value):

                            # There's already a lock for that value, check if we hold it
                            if lock_db_obj["references"] != skel.dbEntity["_id"]:
                                # This value has already been claimed, and not by us
                                # TODO: Use a custom exception class which is catchable with an try/except
                                raise ValueError(
                                    f"The unique value {skel[bone_name]!r} of bone {bone_name!r} "
                                    f"has been recently claimed (by {new_lock_kind=}, {new_lock_value=}).")
                        else:
                            # This value is locked for the first time. The lock's `_id` is the
                            # hash itself, so claiming it is a single atomic `put` on a known
                            # key and the database decides whether it is taken already; going
                            # through a field plus a query would lose that atomicity.
                            db.put(new_lock_kind, {"_id": new_lock_value, "references": skel.dbEntity["_id"]})
                        if new_lock_value in old_unique_values:
                            old_unique_values.remove(new_lock_value)
                    skel.dbEntity["viur"][f"{bone_name}_uniqueIndexValue"] = new_unique_values

                    # Remove any lock-object we're holding for values that we don't have anymore
                    old_lock_kind = f"{skel.kindName}_{bone_name}_uniquePropertyIndex"
                    for old_unique_value in old_unique_values:
                        # Try to delete the old lock
                        if old_lock_obj := db.get(old_lock_kind, old_unique_value):
                            if old_lock_obj["references"] != skel.dbEntity["_id"]:

                                # We've been supposed to have that lock - but we don't.
                                # Don't remove that lock as it now belongs to a different entry
                                logging.critical("Detected Database corruption! A Value-Lock had been reassigned!")
                            else:
                                # It's our lock which we don't need anymore
                                db.delete(old_lock_kind, old_unique_value)
                        else:
                            logging.critical("Detected Database corruption! Could not delete stale lock-object!")

            # Delete legacy property (PR #1244)  #TODO: Remove in ViUR4
            skel.dbEntity.pop("viur_incomming_relational_locks", None)

            # Ensure the SEO-Keys are up-to-date
            last_set_seo_keys = skel.dbEntity["viur"].get("viurCurrentSeoKeys") or {}
            # Filter garbage serialized into this field by the SeoKeyBone
            last_set_seo_keys = {k: v for k, v in last_set_seo_keys.items() if not k.startswith("_") and v}

            if not isinstance(skel.dbEntity["viur"].get("viurCurrentSeoKeys"), dict):
                skel.dbEntity["viur"]["viurCurrentSeoKeys"] = {}

            if current_seo_keys := skel.getCurrentSEOKeys():
                # Convert to lower-case and remove certain characters
                for lang, value in current_seo_keys.items():
                    current_seo_keys[lang] = value.lower().translate(Skeleton.__seo_key_trans).strip()

            for language in (conf.i18n.available_languages or [conf.i18n.default_language]):
                if current_seo_keys and language in current_seo_keys:
                    current_seo_key = current_seo_keys[language]

                    # Start from the key this entry currently holds: it may carry a suffix
                    # from an earlier collision, and that suffix has to survive this write.
                    new_seo_key = last_set_seo_keys.get(language) or current_seo_key
                    if not (new_seo_key == current_seo_key or new_seo_key.startswith(f"{current_seo_key}-")):
                        # The held key no longer derives from the requested one
                        new_seo_key = current_seo_key

                    for _ in range(0, 3):
                        entry_using_key = db.Query(skel.kindName).filter(
                            "viur.viurActiveSeoKeys =", new_seo_key).getEntry()

                        if entry_using_key and entry_using_key["_id"] != skel.dbEntity["_id"]:
                            # It's not unique; append a random string and try again
                            new_seo_key = f"{current_seo_key}-{utils.string.random(5).lower()}"

                        else:
                            # We found a new SeoKey
                            break
                    else:
                        raise ValueError("Could not generate an unique seo key in 3 attempts")

                    last_set_seo_keys[language] = new_seo_key

                else:
                    # We'll use the database-key instead
                    last_set_seo_keys[language] = str(skel.dbEntity["_id"])

                # Store the current, active key for that language
                skel.dbEntity["viur"]["viurCurrentSeoKeys"][language] = last_set_seo_keys[language]

            skel.dbEntity["viur"].setdefault("viurActiveSeoKeys", [])
            for language, seo_key in last_set_seo_keys.items():
                if (
                    skel.dbEntity["viur"]["viurCurrentSeoKeys"][language]
                    not in skel.dbEntity["viur"]["viurActiveSeoKeys"]
                ):
                    # Ensure the current, active seo key is in the list of all seo keys
                    skel.dbEntity["viur"]["viurActiveSeoKeys"].insert(0, seo_key)
            if str(skel.dbEntity["_id"]) not in skel.dbEntity["viur"]["viurActiveSeoKeys"]:
                # Ensure that key is also in there
                skel.dbEntity["viur"]["viurActiveSeoKeys"].insert(0, str(skel.dbEntity["_id"]))
            # Trim to the last 200 used entries
            skel.dbEntity["viur"]["viurActiveSeoKeys"] = skel.dbEntity["viur"]["viurActiveSeoKeys"][:200]
            # Store the requested keys; kept for applications reading this property
            skel.dbEntity["viur"]["viurLastRequestedSeoKeys"] = current_seo_keys

            # mark entity as "dirty" when update_relations is set, to zero otherwise.
            skel.dbEntity["viur"]["delayedUpdateTag"] = time.time() if update_relations else 0

            skel.dbEntity = skel.preProcessSerializedData(skel.dbEntity)

            # Allow the database adapter to apply last minute changes to the object
            for adapter in skel.database_adapters:
                adapter.prewrite(skel, is_add, change_list)

            # ViUR2 import compatibility - remove properties containing. if we have a dict with the same name
            def fixDotNames(entity):
                for k, v in list(entity.items()):
                    if isinstance(v, dict):
                        for k2, v2 in list(entity.items()):
                            if k2.startswith(f"{k}."):
                                del entity[k2]
                                backupKey = k2.replace(".", "__")
                                entity[backupKey] = v2
                                # MongoDB has no per-field index exclusion; every field is
                                # queryable.
                        fixDotNames(v)
                    elif isinstance(v, list):
                        for x in v:
                            if isinstance(x, dict):
                                fixDotNames(x)

            # FIXME: REMOVE IN VIUR4
            if conf.viur2import_blobsource:  # Try to fix these only when converting from ViUR2
                fixDotNames(skel.dbEntity)

            # Write the core entry back
            db.put(skel.kindName, skel.dbEntity)

            # Now write the blob-lock object
            blob_list = skel.preProcessBlobLocks(blob_list)
            if blob_list is None:
                raise ValueError("Did you forget to return the blob_list somewhere inside getReferencedBlobs()?")
            if None in blob_list:
                msg = f"None is not valid in {blob_list=}"
                logging.error(msg)
                raise ValueError(msg)

            if not is_add and (old_blob_lock_obj := db.get("viur-blob-locks", db_key)):
                removed_blobs = set(old_blob_lock_obj.get("active_blob_references", [])) - blob_list
                old_blob_lock_obj["active_blob_references"] = list(blob_list)
                if old_blob_lock_obj["old_blob_references"] is None:
                    old_blob_lock_obj["old_blob_references"] = list(removed_blobs)
                else:
                    old_blob_refs = set(old_blob_lock_obj["old_blob_references"])
                    old_blob_refs.update(removed_blobs)  # Add removed blobs
                    old_blob_refs -= blob_list  # Remove active blobs
                    old_blob_lock_obj["old_blob_references"] = list(old_blob_refs)

                old_blob_lock_obj["has_old_blob_references"] = bool(old_blob_lock_obj["old_blob_references"])
                old_blob_lock_obj["is_stale"] = False
                db.put("viur-blob-locks", old_blob_lock_obj)
            else:  # We need to create a new blob-lock-object
                blob_lock_obj = {
                    "_id": skel.dbEntity["_id"],
                    "active_blob_references": list(blob_list),
                    "old_blob_references": [],
                    "has_old_blob_references": False,
                    "is_stale": False,
                }
                db.put("viur-blob-locks", blob_lock_obj)

            return skel.dbEntity["_id"], write_skel, change_list, is_add

        # Parse provided key, if any, and set it to skel["key"]
        if key:
            skel["key"] = _check_key(key)

        if skel._cascade_deletion is True:
            if skel["key"]:
                logging.info(f"{skel._cascade_deletion=}, will delete {skel["key"]!r}")
                skel.delete()

            return skel

        # Run transactional function
        if db.is_in_transaction():
            key, skel, change_list, is_add = __txn_write(skel)
        else:
            key, skel, change_list, is_add = db.run_in_transaction(__txn_write, skel)

        for bone_name, bone in skel.items():
            bone.postSavedHandler(skel, bone_name, key)

        skel.postSavedHandler(key, skel.dbEntity)

        if update_relations and not is_add:
            if change_list and len(change_list) < 5:  # Only a few bones have changed, process these individually
                tasks.update_relations(key, changed_bones=change_list, _countdown=10)

            else:  # Update all inbound relations, regardless of which bones they mirror
                tasks.update_relations(key)

        # Trigger the database adapter of the changes made to the entry
        for adapter in skel.database_adapters:
            adapter.write(skel, is_add, change_list)

        return skel

    @classmethod
    def delete(cls, skel: SkeletonInstance, key: str | None = None) -> None:
        """
            Deletes the entity associated with the current Skeleton from the data store.

            :param key: Allows to specify a key that is used for deletion, otherwise skel["key"] will be used.
        """

        def __txn_delete(skel: SkeletonInstance, key: str):
            if not skel.read(key):
                raise ValueError("This skeleton is not in the database (anymore?)!")

            # Is there any relation to this Skeleton which prevents the deletion?
            locked_relation = (
                db.Query("viur-relations")
                .filter("dest._id =", key)
                .filter("viur_relational_consistency =", RelationalConsistency.PreventDeletion.value)
            ).getEntry()

            if locked_relation is not None:
                raise errors.Locked("This entry is still referenced by other Skeletons, which prevents deleting!")

            # Ensure that any value lock objects remaining for this entry are being deleted
            viur_data = skel.dbEntity.get("viur") or {}

            for boneName, bone in skel.items():
                bone.delete(skel, boneName)
                if bone.unique:
                    lock_kind = f"{skel.kindName}_{boneName}_uniquePropertyIndex"
                    flushList = []
                    for lockValue in viur_data.get(f"{boneName}_uniqueIndexValue") or []:
                        lockObj = db.get(lock_kind, lockValue)
                        if not lockObj:
                            logging.error(f"{lock_kind=} {lockValue=} missing!")
                        elif lockObj["references"] != key:
                            logging.error(
                                f"""{key!r} does not hold lock for {lock_kind=} {lockValue=}""")
                        else:
                            flushList.append(lockValue)
                    if flushList:
                        db.delete(lock_kind, flushList)

            # Delete the blob-key lock object
            lockObj = db.get("viur-blob-locks", key)

            if lockObj is not None:
                if lockObj["old_blob_references"] is None and lockObj["active_blob_references"] is None:
                    db.delete("viur-blob-locks", key)  # Nothing to do here
                else:
                    if lockObj["old_blob_references"] is None:
                        # No old stale entries, move active_blob_references -> old_blob_references
                        lockObj["old_blob_references"] = lockObj["active_blob_references"]
                    elif lockObj["active_blob_references"] is not None:
                        # Append the current references to the list of old & stale references
                        lockObj["old_blob_references"] += lockObj["active_blob_references"]
                    lockObj["active_blob_references"] = []  # There are no active ones left
                    lockObj["is_stale"] = True
                    lockObj["has_old_blob_references"] = True
                    db.put("viur-blob-locks", lockObj)

            db.delete(skel.kindName, key)
            tasks.update_relations(key)

        if key := (key or skel["key"]):
            key = _check_key(key)
        else:
            raise ValueError("This skeleton has no key!")

        # Full skeleton is required to have all bones!
        skel = skeletonByKind(skel.kindName)()

        if db.is_in_transaction():
            __txn_delete(skel, key)
        else:
            db.run_in_transaction(__txn_delete, skel, key)

        for boneName, bone in skel.items():
            bone.postDeletedHandler(skel, boneName, key)

        skel.postDeletedHandler(key)

        # Inform the custom DB Adapter
        for adapter in skel.database_adapters:
            adapter.delete(skel)

    @classmethod
    def patch(
        cls,
        skel: SkeletonInstance,
        values: t.Optional[dict | t.Callable[[SkeletonInstance], None]] = {},
        *,
        check: t.Optional[dict | t.Callable[[SkeletonInstance], None]] = None,
        create: t.Optional[bool | dict | t.Callable[[SkeletonInstance], None]] = None,
        ignore: t.Optional[t.Iterable[str]] = (),
        internal: bool = True,
        key: str | None = None,
        preprocess: t.Optional[t.Callable[[SkeletonInstance], None]] = None,
        retry: int = 0,
        update_relations: bool = True,
    ) -> SkeletonInstance:
        """
        Performs an edit operation on a Skeleton within a transaction.

        The transaction performs a read, sets bones and afterwards does a write with exclusive access on the
        given Skeleton and its underlying database entity.

        All value-dicts that are being fed to this function are provided to `skel.fromClient()`. Instead of dicts,
        a callable can also be given that can individually modify the Skeleton that is edited.

        :param values: A dict of key-values to update on the entry, or a callable that is executed within
            the transaction.

            This dict allows for a special notation: Keys starting with "+" or "-" are added or substracted to the
            given value, which can be used for counters.
        :param key: The ``_id`` string from which the data shall be fetched.
            If not provided, skel["key"] will be used.
        :param check: An optional dict of key-values or a callable to check on the Skeleton before updating.
            If something fails within this check, an AssertionError is being raised.
        :param create: Allows to specify a dict or initial callable that is executed in case the Skeleton with the
            given key does not exist.
        :param update_relations: Trigger update relations task on success. Defaults to False.
        :param ignore: optional list of bones to be ignored from values; Defaults to an empty list,
            so that all bones are accepted (even read-only ones, as skel.patch() is being used internally)
        :param internal: Internal patch does ignore any NotSet and Empty errors that may raise in skel.fromClient()
        :param retry: On RuntimeError, retry for this amount of times. - DEPRECATED!

        If the function does not raise an Exception, all went well.
        The function always returns the input Skeleton.

        Raises:
            ValueError: In case parameters where given wrong or incomplete.
            AssertionError: In case an asserted check parameter did not match.
            ReadFromClientException: In case a skel.fromClient() failed with a high severity.
        """

        # Transactional function
        def __update_txn():
            # Try to read the skeleton, create on demand
            if not skel.read(key):
                if create is None or create is False:
                    raise ValueError("Creation during update is forbidden - explicitly provide `create=True` to allow.")

                if not (key or skel["key"]) and create in (False, None):
                    return ValueError("No valid key provided")

                if key or skel["key"]:
                    skel["key"] = _check_key(key or skel["key"])

                if isinstance(create, dict):
                    if create and not skel.fromClient(create, amend=True, ignore=ignore):
                        raise ReadFromClientException(skel.errors)
                elif callable(create):
                    create(skel)
                elif create is not True:
                    raise ValueError("'create' must either be dict or a callable.")

            # Handle check
            if isinstance(check, dict):
                for bone, value in check.items():
                    if skel[bone] != value:
                        raise AssertionError(f"{bone} contains {skel[bone]!r}, expecting {value!r}")

            elif callable(check):
                check(skel)

            # Set values
            if isinstance(values, dict):
                if values and not skel.fromClient(values, amend=True, ignore=ignore) and not internal:
                    raise ReadFromClientException(skel.errors)

                # In case we're in internal-mode, only raise fatal errors.
                if skel.errors and internal:
                    for error in skel.errors:
                        if error.severity in (
                                ReadFromClientErrorSeverity.Invalid,
                                ReadFromClientErrorSeverity.InvalidatesOther,
                        ):
                            raise ReadFromClientException(skel.errors)

                    # otherwise, ignore any reported errors
                    skel.errors.clear()

                # Special-feature: "+" and "-" prefix for simple calculations
                # TODO: This can maybe integrated into skel.fromClient() later...
                for name, value in values.items():
                    match name[0]:
                        case "+":  # Increment by value?
                            skel[name[1:]] += value
                        case "-":  # Decrement by value?
                            skel[name[1:]] -= value

            elif callable(values):
                values(skel)

            else:
                raise ValueError("'values' must either be dict or a callable.")

            # Run preprocess hook
            if preprocess:
                preprocess(skel)

            # Finally write the skeleton
            return skel.write(update_relations=update_relations)

        if not db.is_in_transaction():
            # Retry loop
            while True:
                try:
                    return db.run_in_transaction(__update_txn)

                except RuntimeError as e:
                    retry -= 1
                    if retry < 0:
                        raise

                    logging.debug(f"{e}, retrying {retry} more times")

                time.sleep(1)
        else:
            return __update_txn()

    @classmethod
    def preProcessBlobLocks(cls, skel: SkeletonInstance, locks):
        """
            Can be overridden to modify the list of blobs referenced by this skeleton
        """
        return locks

    @classmethod
    def preProcessSerializedData(cls, skel: SkeletonInstance, entity):
        """
            Can be overridden to modify the entity document (a ``dict``) before its actually
            written to the data store.
        """
        return entity

    @classmethod
    def postSavedHandler(cls, skel: SkeletonInstance, key, dbObj):
        """
            Can be overridden to perform further actions after the entity has been written
            to the data store.
        """
        pass

    @classmethod
    def postDeletedHandler(cls, skel: SkeletonInstance, key):
        """
            Can be overridden to perform further actions after the entity has been deleted
            from the data store.
        """
        pass

    @classmethod
    def getCurrentSEOKeys(cls, skel: SkeletonInstance) -> None | dict[str, str]:
        """
        Should be overridden to return a dictionary of language -> SEO-Friendly key
        this entry should be reachable under. How theses names are derived are entirely up to the application.
        If the name is already in use for this module, the server will automatically append some random string
        to make it unique.
        :return:
        """
        return
