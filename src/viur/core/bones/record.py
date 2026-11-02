import json
import logging
import typing as t

from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
from viur.core import db, utils, i18n

if t.TYPE_CHECKING:
    from ..skeleton import SkeletonInstance


class RecordBone(BaseBone):
    """
    The RecordBone class is a specialized bone type used to store structured data. It inherits from
    the BaseBone class. The RecordBone class is designed to store complex data structures, such as
    nested dictionaries or objects, by using a related skeleton class (the using parameter) to manage
    the internal structure of the data.

    :param format: Optional string parameter to specify the format of the record bone.
    :param indexed: Optional boolean parameter to indicate if the record bone is indexed.
        Defaults to False.
    :param using: A class that inherits from 'viur.core.skeleton.RelSkel' to be used with the
        RecordBone.
    :param kwargs: Additional keyword arguments to be passed to the BaseBone constructor.
    """
    type = "record"

    def __init__(
        self,
        *,
        format: str = None,
        indexed: bool = False,
        using: 'viur.core.skeleton.RelSkel' = None,
        **kwargs
    ):
        from viur.core.skeleton.relskel import RelSkel
        if not issubclass(using, RelSkel):
            raise ValueError("RecordBone requires for valid using-parameter (subclass of viur.core.skeleton.RelSkel)")

        super().__init__(indexed=indexed, **kwargs)
        self.using = using
        self.format = format
        if not format or indexed:
            raise NotImplementedError("A RecordBone must not be indexed and must have a format set")

    def singleValueUnserialize(self, val):
        """
        Unserializes a single value, creating an instance of the 'using' class and unserializing
        the value into it.

        :param val: The value to unserialize.
        :return: An instance of the 'using' class with the unserialized data.
        :raises AssertionError: If the unserialized value is not a dictionary.
        """
        if isinstance(val, str):
            try:
                value = json.loads(val)
            except ValueError:
                value = None
        else:
            value = val

        if not value:
            return None

        if isinstance(value, list) and value:
            value = value[0]

        assert isinstance(value, dict), f"Read {value=} ({type(value)})"

        usingSkel = self.using()
        usingSkel.unserialize(value)
        return usingSkel

    def singleValueSerialize(self, value, skel: 'SkeletonInstance', name: str, parentIndexed: bool):
        """
        Serializes a single value by calling the serialize method of the 'using' skeleton instance.

        :param value: The value to be serialized, which should be an instance of the 'using' skeleton.
        :param skel: The parent skeleton instance.
        :param name: The name of the bone.
        :param parentIndexed: A boolean indicating if the parent bone is indexed.
        :return: The serialized value.
        """
        if not value:
            return None

        return value.serialize(parentIndexed=False)

    def _get_single_destinct_hash(self, value):
        return tuple(bone._get_destinct_hash(value, name) for name, bone in self.using.__boneMap__.items())

    def parseSubfieldsFromClient(self) -> bool:
        """
        Determines if the current request should attempt to parse subfields received from the client.
        This should only be set to True if a list of dictionaries is expected to be transmitted.
        """
        return True

    def singleValueFromClient(self, value, skel, bone_name, client_data):
        usingSkel = self.using()

        if not usingSkel.fromClient(value):
            usingSkel.errors.append(
                ReadFromClientError(
                    ReadFromClientErrorSeverity.Invalid,
                    i18n.translate("core.bones.error.incomplete", "Incomplete data"),
                )
            )

        return usingSkel, usingSkel.errors

    def postSavedHandler(self, skel, boneName, key) -> None:
        super().postSavedHandler(skel, boneName, key)

        relational_bone_names = {
            name for name, bone in self.using.__boneMap__.items()
            if utils.string.is_prefix(bone.type, "relational")
        }
        saved_paths = set()
        truncated = False

        for idx, lang, value in self.iter_bone_value(skel, boneName):
            if idx is not None and idx > 99:
                logging.warning("postSavedHandler entry limit maximum reached")
                truncated = True
                break

            for sub_bone_name, bone in value.items():
                path = ".".join(name for name in (boneName, lang, f"{idx or 0:02}", sub_bone_name) if name)
                if sub_bone_name in relational_bone_names:
                    saved_paths.add(path)

                bone.postSavedHandler(value, path, key)

        if relational_bone_names and not truncated:
            self._drop_stale_relations(boneName, key, relational_bone_names, saved_paths)

    def _drop_stale_relations(
        self,
        bone_name: str,
        key: db.Key,
        relational_bone_names: set[str],
        saved_paths: set[str],
    ) -> None:
        """
        Delete the ``viur-relations`` entries of record values which no longer exist.

        A relation is considered stale when its ``viur_src_property`` has the shape
        ``<bone_name>[.<lang>].<index>.<sub_bone_name>`` of a known relational sub-bone,
        but was not written by the current save (e.g. the list has been shortened or emptied).

        Relations of other bones, of nested containers, of unknown sub-bones or unknown languages
        are left untouched; they may belong to another version of the application.

        :param bone_name: The name (or path, if nested) of this bone.
        :param key: The key of the saved skeleton.
        :param relational_bone_names: Names of the relational sub-bones of the using-skeleton.
        :param saved_paths: The ``viur_src_property`` paths written by the current save.
        """
        query = db.Query("viur-relations") \
            .filter("viur_src_kind =", key.kind) \
            .filter("src.__key__ =", key) \
            .filter("viur_src_property >", f"{bone_name}.") \
            .filter("viur_src_property <", f"{bone_name}.\ufffd")

        stale_keys = []

        for entity in query.iter():
            path = entity["viur_src_property"]
            if path in saved_paths:  # still in use, just written by the sub-bone's postSavedHandler
                continue

            # Split "<bone_name>.[<lang>.]<index>.<sub_bone_name>" behind the prefix, e.g. ["de", "01", "image"].
            # Paths with more parts belong to a nested container, which cleans up its own relations.
            parts = path[len(bone_name) + 1:].split(".")
            if self.languages:
                if len(parts) != 3 or parts[0] not in self.languages:
                    continue
            elif len(parts) != 2:
                continue

            # Only drop relations this bone is responsible for; unknown sub-bones may belong to another app version
            *_, index, sub_bone_name = parts
            if index.isdigit() and sub_bone_name in relational_bone_names:
                stale_keys.append(entity.key)

        if stale_keys:
            logging.debug(f"Delete {len(stale_keys)} stale viur-relations of {bone_name!r}")
            db.delete(stale_keys)

    def postDeletedHandler(self, skel, boneName, key) -> None:
        super().postDeletedHandler(skel, boneName, key)

        for idx, lang, value in self.iter_bone_value(skel, boneName):
            for sub_bone_name, bone in value.items():
                path = ".".join(part for part in (boneName, lang, f"{idx or 0:02}", sub_bone_name) if part)
                bone.postDeletedHandler(value, path, key)

    def getSearchTags(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str) -> set[str]:
        """
        Collects search tags from the 'using' skeleton instance for the given bone.

        :param skel: The parent skeleton instance.
        :param name: The name of the bone.
        :return: A set of search tags generated from the 'using' skeleton instance.
        """
        result = set()

        for _, lang, value in self.iter_bone_value(skel, name):
            if value is None:
                continue

            for key, bone in value.items():
                if not bone.searchable:
                    continue

                for tag in bone.getSearchTags(value, key):
                    result.add(tag)

        return result

    def getSearchDocumentFields(self, valuesCache, name, prefix=""):
        """
        Generates a list of search document fields for the given values cache, name, and optional prefix.

        :param dict valuesCache: A dictionary containing the cached values.
        :param str name: The name of the bone to process.
        :param str prefix: An optional prefix to use for the search document fields, defaults to an empty string.
        :return: A list of search document fields.
        :rtype: list
        """

        def getValues(res, skel, valuesCache, searchPrefix):
            for key, bone in skel.items():
                if bone.searchable:
                    res.extend(bone.getSearchDocumentFields(valuesCache, key, prefix=searchPrefix))

        value = valuesCache.get(name)
        res = []

        if not value:
            return res
        uskel = self.using()
        for idx, val in enumerate(value):
            getValues(res, uskel, val, f"{prefix}{name}_{idx}")

        return res

    def getReferencedBlobs(self, skel: "SkeletonInstance", name: str) -> set[str]:
        """
        Retrieves a set of referenced blobs for the given skeleton instance and name.

        :param skel: The skeleton instance to process.
        :param name: The name of the bone to process.
        :return: A set of referenced blobs.
        """
        result = set()

        for _, lang, value in self.iter_bone_value(skel, name):
            if value is None:
                continue

            for key, bone in value.items():
                result |= bone.getReferencedBlobs(value, key)

        return result

    def getUniquePropertyIndexValues(self, valuesCache: dict, name: str) -> list[str]:
        """
        This method is intentionally not implemented as it's not possible to determine how to derive
        a key from the related skeleton being used (i.e., which fields to include and how).

        """
        raise NotImplementedError()

    def structure(self) -> dict:
        return super().structure() | {
            "format": self.format,
            "using": self.using().structure(),
        }

    def _atomic_dump(self, value: "SkeletonInstance") -> dict | None:
        if value is not None:
            return value.dump()

    def refresh(self, skel, bone_name):
        for _, _, using_skel in self.iter_bone_value(skel, bone_name):
            for key, bone in using_skel.items():
                bone.refresh(using_skel, key)

                # When the value (acting as a skel) is marked for deletion, clear it.
                if using_skel._cascade_deletion is True:
                    # Unset the Entity, so the skeleton becomes a False truthyness.
                    using_skel.setEntity(db.Entity())
