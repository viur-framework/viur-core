import json
import logging
import typing as t

from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
from viur.core import db, utils, tasks, i18n

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
        return tuple(bone._get_destinct_hash(value[name]) for name, bone in self.using.__boneMap__.items())

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

        drop_relations_higher = {}

        for idx, lang, value in self.iter_bone_value(skel, boneName):
            if idx > 99:
                logging.warning("postSavedHandler entry limit maximum reached")
                drop_relations_higher.clear()
                break

            for sub_bone_name, bone in value.items():
                path = ".".join(name for name in (boneName, lang, f"{idx:02}", sub_bone_name) if name)
                if utils.string.is_prefix(bone.type, "relational"):
                    drop_relations_higher[sub_bone_name] = path

                bone.postSavedHandler(value, path, key)

        if drop_relations_higher:
            for viur_src_property in drop_relations_higher.values():
                query = db.Query("viur-relations") \
                    .filter("viur_src_kind =", key.kind) \
                    .filter("src.__key__ =", key) \
                    .filter("viur_src_property >", viur_src_property)

                logging.debug(f"Delete viur-relations with {query=}")
                tasks.DeleteEntitiesIter.startIterOnQuery(query)

    def postDeletedHandler(self, skel, boneName, key) -> None:
        super().postDeletedHandler(skel, boneName, key)

        for idx, lang, value in self.iter_bone_value(skel, boneName):
            for sub_bone_name, bone in value.items():
                path = ".".join(name for name in (boneName, lang, f"{idx:02}", sub_bone_name) if name)
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
