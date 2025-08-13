"""
This module contains the RelationalBone to create and manage relationships between skeletons
and enums to parameterize it.
"""
import enum
import json
import logging
import time
import typing as t
import warnings
from itertools import chain

from viur.core import db, utils, i18n
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity, getSystemInitialized

if t.TYPE_CHECKING:
    from viur.core.skeleton import SkeletonInstance, RelSkel


class RelationalConsistency(enum.IntEnum):
    """
    An enumeration representing the different consistency strategies for handling stale relations in
    the RelationalBone class.
    """
    Ignore = 1
    """Ignore stale relations, which represents the old behavior."""
    PreventDeletion = 2
    """Lock the target object so that it cannot be deleted."""
    SetNull = 3
    """Drop the relation if the target object is deleted."""
    CascadeDeletion = 4
    """
    .. warning:: Delete this object also if the referenced entry is deleted (Dangerous!)
    """


class RelationalUpdateLevel(enum.Enum):
    """
    An enumeration representing the different update levels for the RelationalBone class.
    """
    Always = 0
    """Always update the relational information, regardless of the context."""
    OnRebuildSearchIndex = 1
    """Update the relational information only when rebuilding the search index."""
    OnValueAssignment = 2
    """Update the relational information only when a new value is assigned to the bone."""


class RelDict(t.TypedDict):
    dest: "SkeletonInstance"
    rel: t.Optional["RelSkel"]


class RelationalBone(BaseBone):
    """
    The base class for all relational bones in the ViUR framework.
    RelationalBone is used to create and manage relationships between database entities. This class provides
    basic functionality and attributes that can be extended by other specialized relational bone classes,
    such as N1Relation, N2NRelation, and Hierarchy.
    This implementation prioritizes read efficiency and is suitable for situations where data is read more
    frequently than written. However, it comes with increased write operations when writing an entity to the
    database. The additional write operations depend on the type of relationship: multiple=True RelationalBones
    or 1:N relations.

    The implementation does not instantly update relational information when a skeleton is updated; instead,
    it triggers a deferred task to update references. This may result in outdated data until the task is completed.

    Note: Filtering a list by relational properties uses the outdated data.

    Example:
    - Entity A references Entity B.
    - Both have a property "name."
    - Entity B is updated (its name changes).
    - Entity A's RelationalBone values still show Entity B's old name.

    It is not recommended for cases where data is read less frequently than written, as there is no
    write-efficient method available yet.

    :param kind: KindName of the referenced property.
    :param module: Name of the module which should be used to select entities of kind "kind". If not set,
        the value of "kind" will be used (the kindName must match the moduleName)
    :param refKeys: A list of properties to include from the referenced property. These properties will be
        available in the template without having to fetch the referenced property. Filtering is also only possible
        by properties named here!
    :param parentKeys: A list of properties from the current skeleton to include. If mixing filtering by
        relational properties and properties of the class itself, these must be named here.
    :param multiple: If True, allow referencing multiple Elements of the given class. (Eg. n:n-relation).
        Otherwise its n:1, (you can only select exactly one). It's possible to use a unique constraint on this
        bone, allowing for at-most-1:1 or at-most-1:n relations. Instead of true, it's also possible to use
        a ```class MultipleConstraints``` instead.

    :param format:
        Hint for the frontend how to display such an relation. This is now a python expression
        evaluated by safeeval on the client side. The following values will be passed to the expression:

            - value
                The value to display. This will be always a dict (= a single value) - even if the relation is
                multiple (in which case the expression is evaluated once per referenced entity)

            - structure
                The structure of the skeleton this bone is part of as a dictionary as it's transferred to the
                fronted by the admin/vi-render.

            - language
                The current language used by the frontend in ISO2 code (eg. "de"). This will be always set, even if
                the project did not enable the multi-language feature.

    :param updateLevel:
        Indicates how ViUR should keep the values copied from the referenced entity into our
        entity up to date. If this bone is indexed, it's recommended to leave this set to
        RelationalUpdateLevel.Always, as filtering/sorting by this bone will produce stale results.

            :param RelationalUpdateLevel.Always:

                always update refkeys (old behavior). If the referenced entity is edited, ViUR will update this
                entity also (after a small delay, as these updates happen deferred)

            :param RelationalUpdateLevel.OnRebuildSearchIndex:

                update refKeys only on rebuildSearchIndex. If the referenced entity changes, this entity will
                remain unchanged (this RelationalBone will still have the old values), but it can be updated
                by either by editing this entity or running a rebuildSearchIndex over our kind.

            :param RelationalUpdateLevel.OnValueAssignment:

                update only if explicitly set. A rebuildSearchIndex will not trigger an update, this bone has to be
                explicitly modified (in an edit) to have it's values updated

    :param consistency:
        Can be used to implement SQL-like constrains on this relation. Possible values are:
            - RelationalConsistency.Ignore
                If the referenced entity gets deleted, this bone will not change. It will still reflect the old
                values. This will be even be preserved over edits, however if that referenced value is once
                deleted by the user (assigning a different value to this bone or removing that value of the list
                of relations if we are multiple) there's no way of restoring it

            - RelationalConsistency.PreventDeletion
                Will prevent deleting the referenced entity as long as it's selected in this bone (calling
                skel.delete() on the referenced entity will raise errors.Locked). It's still (technically)
                possible to remove the underlying datastore entity using db.delete manually, but this *must not*
                be used on a skeleton object as it will leave a whole bunch of references in a stale state.

            - RelationalConsistency.SetNull
                Will set this bone to None (or remove the relation from the list in
                case we are multiple) when the referenced entity is deleted.

            - RelationalConsistency.CascadeDeletion:
                (Dangerous!) Will delete this entity when the referenced entity is deleted. Warning: Unlike
                relational updates this will cascade. If Entity A references B with CascadeDeletion set, and
                B references C also with CascadeDeletion; if C gets deleted, both B and A will be deleted as well.

    """
    type = "relational"
    kind = None

    def __init__(
        self,
        *,
        consistency: RelationalConsistency = RelationalConsistency.Ignore,
        format: str = "$(dest.name)",
        kind: str = None,
        module: t.Optional[str] = None,
        parentKeys: t.Optional[t.Iterable[str]] = {"name"},
        refKeys: t.Optional[t.Iterable[str]] = {"name"},
        updateLevel: RelationalUpdateLevel = RelationalUpdateLevel.Always,
        using: t.Optional["RelSkel"] = None,
        **kwargs
    ):
        """
            Initialize a new RelationalBone.

            :param kind:
                KindName of the referenced property.
            :param module:
                Name of the module which should be used to select entities of kind "type". If not set,
                the value of "type" will be used (the kindName must match the moduleName)
            :param refKeys:
                An iterable of properties to include from the referenced property. These properties will be
                available in the template without having to fetch the referenced property. Filtering is also only
                possible by properties named here!
            :param parentKeys:
                An iterable of properties from the current skeleton to include. If mixing filtering by
                relational properties and properties of the class itself, these must be named here.
            :param multiple:
                If True, allow referencing multiple Elements of the given class. (Eg. n:n-relation).
                Otherwise its n:1, (you can only select exactly one). It's possible to use a unique constraint on this
                bone, allowing for at-most-1:1 or at-most-1:n relations. Instead of true, it's also possible to use
                a :class:MultipleConstraints instead.

            :param format: Hint for the frontend how to display such an relation. This is now a python expression
                evaluated by safeeval on the client side. The following values will be passed to the expression

                :param value:
                    The value to display. This will be always a dict (= a single value) - even if the
                    relation is multiple (in which case the expression is evaluated once per referenced entity)
                :param structure:
                    The structure of the skeleton this bone is part of as a dictionary as it's
                    transferred to the fronted by the admin/vi-render.
                :param language:
                    The current language used by the frontend in ISO2 code (eg. "de"). This will be
                    always set, even if the project did not enable the multi-language feature.

            :param updateLevel:
                Indicates how ViUR should keep the values copied from the referenced entity into our
                entity up to date. If this bone is indexed, it's recommended to leave this set to
                RelationalUpdateLevel.Always, as filtering/sorting by this bone will produce stale results.

                    :param RelationalUpdateLevel.Always:
                        always update refkeys (old behavior). If the referenced entity is edited, ViUR will update this
                        entity also (after a small delay, as these updates happen deferred)
                    :param RelationalUpdateLevel.OnRebuildSearchIndex:
                        update refKeys only on rebuildSearchIndex. If the
                        referenced entity changes, this entity will remain unchanged
                        (this RelationalBone will still have the old values), but it can be updated
                        by either by editing this entity or running a rebuildSearchIndex over our kind.
                    :param RelationalUpdateLevel.OnValueAssignment:
                        update only if explicitly set. A rebuildSearchIndex will not trigger
                        an update, this bone has to be explicitly modified (in an edit) to have it's values updated

            :param consistency:
                Can be used to implement SQL-like constrains on this relation.

                    :param RelationalConsistency.Ignore:
                        If the referenced entity gets deleted, this bone will not change. It
                        will still reflect the old values. This will be even be preserved over edits, however if that
                        referenced value is once deleted by the user (assigning a different value to this bone or
                        removing that value of the list of relations if we are multiple) there's no way of restoring it

                    :param RelationalConsistency.PreventDeletion:
                        Will prevent deleting the referenced entity as long as it's
                        selected in this bone (calling skel.delete() on the referenced entity will raise errors.Locked).
                        It's still (technically) possible to remove the underlying datastore entity using db.delete
                        manually, but this *must not* be used on a skeleton object as it will leave a whole bunch of
                        references in a stale state.

                    :param RelationalConsistency.SetNull:
                        Will set this bone to None (or remove the relation from the list in
                        case we are multiple) when the referenced entity is deleted.

                    :param RelationalConsistency.CascadeDeletion:
                        (Dangerous!) Will delete this entity when the referenced entity
                        is deleted. Warning: Unlike relational updates this will cascade. If Entity A references B with
                        CascadeDeletion set, and B references C also with CascadeDeletion; if C gets deleted, both B and
                        A will be deleted as well.
        """
        super().__init__(**kwargs)
        self.format = format

        if kind:
            self.kind = kind

        if module:
            self.module = module
        elif self.kind:
            self.module = self.kind

        if self.kind is None or self.module is None:
            raise NotImplementedError("'kind' and 'module' of RelationalBone must not be None")

        # Referenced keys
        self.refKeys = {"key"}
        if refKeys:
            self.refKeys |= set(refKeys)

        # Parent keys
        self.parentKeys = {"key"}
        if parentKeys:
            self.parentKeys |= set(parentKeys)

        self.using = using

        # FIXME: Remove in VIUR4!!
        if isinstance(updateLevel, int):
            msg = f"parameter updateLevel={updateLevel} in RelationalBone is deprecated. " \
                  f"Please use the RelationalUpdateLevel enum instead"
            logging.warning(msg, stacklevel=3)
            warnings.warn(msg, DeprecationWarning, stacklevel=3)

            assert 0 <= updateLevel < 3
            for n in RelationalUpdateLevel:
                if updateLevel == n.value:
                    updateLevel = n

        self.updateLevel = updateLevel
        self.consistency = consistency

        if getSystemInitialized():
            from viur.core.skeleton import RefSkel, SkeletonInstance
            self._refSkelCache = RefSkel.fromSkel(self.kind, *self.refKeys)
            self._skeletonInstanceClassRef = SkeletonInstance
            self._ref_keys = set(self._refSkelCache.__boneMap__.keys())

    def setSystemInitialized(self):
        """
        Set the system initialized for the current class and cache the RefSkel and SkeletonInstance.

        This method calls the superclass's setSystemInitialized method and initializes the RefSkel
        and SkeletonInstance classes. The RefSkel is created from the current kind and refKeys,
        while the SkeletonInstance class is stored as a reference.

        :rtype: None
        """
        super().setSystemInitialized()
        from viur.core.skeleton import RefSkel, SkeletonInstance

        try:
            self._refSkelCache = RefSkel.fromSkel(self.kind, *self.refKeys)
        except AssertionError:
            raise NotImplementedError(
                f"Skeleton {self.skel_cls!r} {self.__class__.__name__} {self.name!r}: Kind {self.kind!r} unknown"
            )

        self._skeletonInstanceClassRef = SkeletonInstance
        self._ref_keys = set(self._refSkelCache.__boneMap__.keys())

    def _getSkels(self):
        """
        Retrieve the reference skeleton and the 'using' skeleton for the current RelationalBone instance.

        This method returns a tuple containing the reference skeleton (RefSkel) and the 'using' skeleton
        (UsingSkel) associated with the current RelationalBone instance. The 'using' skeleton is only
        retrieved if the 'using' attribute is defined.

        :return: A tuple containing the reference skeleton and the 'using' skeleton.
        :rtype: tuple
        """
        refSkel = self._refSkelCache()
        usingSkel = self.using() if self.using else None
        return refSkel, usingSkel

    def singleValueUnserialize(self, val):
        """
        Restore a value, including the Rel- and Using-Skeleton, from the serialized data read from the datastore.

        This method takes a serialized value from the datastore, deserializes it, and returns the corresponding
        value with restored RelSkel and Using-Skel. It also handles ViUR 2 compatibility by handling string values.

        :param val: A JSON-encoded datastore property.
        :type val: str or dict
        :return: The deserialized value with restored RelSkel and Using-Skel.
        :rtype: dict

        :raises AssertionError: If the deserialized value is not a dictionary.
        """

        def fixFromDictToEntry(inDict):
            """
            Convert a dictionary to an entry with properly restored keys and values.

            :param dict inDict: The input dictionary to convert.
        :   return: The resulting entry.
            :rtype: dict
            """
            if not isinstance(inDict, dict):
                return None
            res = {}
            if "dest" in inDict:
                res["dest"] = db.Entity()
                for k, v in inDict["dest"].items():
                    res["dest"][k] = v
                if "key" in res["dest"]:
                    res["dest"].key = db.normalize_key(res["dest"]["key"])
            if "rel" in inDict and inDict["rel"]:
                res["rel"] = db.Entity()
                for k, v in inDict["rel"].items():
                    res["rel"][k] = v
            else:
                res["rel"] = None
            return res

        if isinstance(val, str):  # ViUR2 compatibility
            try:
                value = json.loads(val)
                if isinstance(value, list):
                    value = [fixFromDictToEntry(x) for x in value]
                elif isinstance(value, dict):
                    value = fixFromDictToEntry(value)
                else:
                    value = None
            except ValueError:
                value = None
        else:
            value = val
        if not value:
            return None
        elif isinstance(value, list) and value:
            value = value[0]
        assert isinstance(value, dict), f"Read something from the datastore thats not a dict: {type(value)}"
        if "dest" not in value:
            return None
        relSkel, usingSkel = self._getSkels()
        relSkel.unserialize(value["dest"])
        if self.using is not None:
            usingSkel.unserialize(value["rel"] or db.Entity())
            usingData = usingSkel
        else:
            usingData = None
        return {"dest": relSkel, "rel": usingData}

    def serialize(self, skel: "SkeletonInstance", name: str, parentIndexed: bool) -> bool:
        """
        Serialize the RelationalBone for the given skeleton, updating relational locks as necessary.

        This method serializes the RelationalBone values for a given skeleton and stores the serialized
        values in the skeleton's dbEntity. It also updates the relational locks, adding new locks and
        removing old ones as needed.

        :param SkeletonInstance skel: The skeleton instance containing the values to be serialized.
        :param str name: The name of the bone to be serialized.
        :param bool parentIndexed: A flag indicating whether the parent bone is indexed.
        :return: True if the serialization is successful, False otherwise.
        :rtype: bool

        :raises AssertionError: If a programming error is detected.
        """

        def serialize_dest_rel(in_value: dict | None = None) -> (dict | None, dict | None):
            if not in_value:
                return None, None
            if dest_val := in_value.get("dest"):
                ref_data_serialized = dest_val.serialize(parentIndexed=indexed)
            else:
                ref_data_serialized = None
            if rel_data := in_value.get("rel"):
                using_data_serialized = rel_data.serialize(parentIndexed=indexed)
            else:
                using_data_serialized = None

            return using_data_serialized, ref_data_serialized


        super().serialize(skel, name, parentIndexed)

        # Clean old properties from entry (prevent name collision)
        for key in tuple(skel.dbEntity.keys()):
            if key.startswith(f"{name}."):
                del skel.dbEntity[key]

        indexed = self.indexed and parentIndexed

        if not (new_vals := skel.accessedValues.get(name)):
            return False

        # TODO: The good old leier... modernize this.
        if self.languages:
            res = {"_viurLanguageWrapper_": True}
            for language in self.languages:
                if language in new_vals:
                    if self.multiple:
                        res[language] = []
                        for val in new_vals[language]:
                            if val:
                                using_data, ref_data = serialize_dest_rel(val)
                                res[language].append({"rel": using_data, "dest": ref_data})
                    else:
                        if (val := new_vals[language]) and val["dest"]:
                            using_data, ref_data = serialize_dest_rel(val)
                            res[language] = {"rel": using_data, "dest": ref_data}
        elif self.multiple:
            res = []
            for val in new_vals:
                if val:
                    using_data, ref_data = serialize_dest_rel(val)
                    res.append({"rel": using_data, "dest": ref_data})
        elif new_vals:
            using_data, ref_data = serialize_dest_rel(new_vals)
            res = {"rel": using_data, "dest": ref_data}

        skel.dbEntity[name] = res

        # Ensure our indexed flag is up2date
        if indexed and name in skel.dbEntity.exclude_from_indexes:
            skel.dbEntity.exclude_from_indexes.discard(name)
        elif not indexed and name not in skel.dbEntity.exclude_from_indexes:
            skel.dbEntity.exclude_from_indexes.add(name)

        # Delete legacy property (PR #1244)  #TODO: Remove in ViUR4
        skel.dbEntity.pop(f"{name}_outgoingRelationalLocks", None)

        return True

    def _get_single_destinct_hash(self, value):
        parts = [value["dest"]["key"]]

        if self.using:
            for name, bone in self.using.__boneMap__.items():
                parts.append(bone._get_destinct_hash(value["rel"][name]))

        return tuple(parts)

    def postSavedHandler(self, skel, boneName, key) -> None:
        """
        Handle relational updates after a skeleton is saved.

        This method updates, removes, or adds relations between the saved skeleton and the referenced entities.
        It also takes care of updating the relational properties and consistency levels.

        :param skel: The saved skeleton instance.
        :param boneName: The name of the relational bone.
        :param key: The key of the saved skeleton instance.
        """
        viur_src_kind = key.kind
        viur_src_property = boneName

        # Hack for RelationalBones in containers (like RecordBones)
        if "." in boneName:
            _, boneName = boneName.rsplit(".", 1)  # bone name to fummel out of the skeleton (again...)

        if not skel[boneName]:
            values = []
        elif self.multiple and self.languages:
            values = chain(*skel[boneName].values())
        elif self.languages:
            values = list(skel[boneName].values())
        elif self.multiple:
            values = skel[boneName]
        else:
            values = [skel[boneName]]

        # Keep a set of all referenced keys
        values = [value for value in values if value]
        values_keys = {value["dest"]["key"] for value in values}

        # Referenced parent values
        src_values = db.Entity(key)
        if skel.dbEntity:
            src_values |= {bone: skel.dbEntity.get(bone) for bone in self.parentKeys or ()}

        # Now is now, nana nananaaaaaaa...
        now = time.time()

        # Helper fcuntion to
        def __update_relation(entity: db.Entity, data: dict):
            ref_skel = data["dest"]
            rel_skel = data["rel"]

            entity["dest"] = ref_skel.serialize(parentIndexed=True)
            entity["rel"] = rel_skel.serialize(parentIndexed=True) if rel_skel else None
            entity["src"] = src_values

            entity["viur_src_kind"] = viur_src_kind
            entity["viur_src_property"] = viur_src_property
            entity["viur_dest_kind"] = self.kind
            entity["viur_delayed_update_tag"] = now
            entity["viur_relational_updateLevel"] = self.updateLevel.value
            entity["viur_relational_consistency"] = self.consistency.value
            entity["viur_foreign_keys"] = list(self.refKeys)
            entity["viurTags"] = skel.dbEntity.get("viurTags") if skel.dbEntity else None

            db.put(entity)

        # Query and update existing entries pointing to this bone
        query = db.Query("viur-relations") \
            .filter("viur_src_kind =", viur_src_kind) \
            .filter("viur_dest_kind =", self.kind) \
            .filter("viur_src_property =", viur_src_property) \
            .filter("src.__key__ =", key)

        for entity in query.iter():
            try:
                if entity["dest"].key not in values_keys:  # Relation has been removed
                    db.delete(entity.key)
                    continue

            except KeyError:  # This entry is corrupt
                db.delete(entity.key)

            else:  # Relation: Updated
                # Find the newest item matching this key (this has to been done this way)...
                value = [value for value in values if value["dest"]["key"] == entity["dest"].key][0]
                # ... and remove it from the list of values
                values.remove(value)
                values_keys.remove(value["dest"]["key"])

                # Update existing database entry
                __update_relation(entity, value)

        # Add new database entries for the remaining values
        for value in values:
            __update_relation(db.Entity(db.Key("viur-relations", parent=key)), value)

    def postDeletedHandler(self, skel: "SkeletonInstance", boneName: str, key: db.Key) -> None:
        """
        Handle relational updates after a skeleton is deleted.

        This method deletes all relations associated with the deleted skeleton and the referenced entities
        for the given relational bone.

        :param skel: The deleted SkeletonInstance.
        :param boneName: The name of the RelationalBone in the Skeleton.
        :param key: The key of the deleted Entity.
        """
        query = db.Query("viur-relations") \
            .filter("viur_src_kind =", key.kind) \
            .filter("viur_dest_kind =", self.kind) \
            .filter("viur_src_property =", boneName) \
            .filter("src.__key__ =", key)

        db.delete([entity for entity in query.run()])

    def isInvalid(self, key) -> None:
        """
        Check if the given key is invalid for this relational bone.

        This method always returns None, as the actual validation of the key
        is performed in other methods of the RelationalBone class.

        :param key: The key to be checked for validity.
        :return: None, as the actual validation is performed elsewhere.
        """
        return None

    def parseSubfieldsFromClient(self):
        """
        Determine if the RelationalBone should parse subfields from the client.

        This method returns True if the `using` attribute is not None, indicating
        that this RelationalBone has a using-skeleton, and its subfields should
        be parsed. Otherwise, it returns False.

        :return: True if the using-skeleton is not None and subfields should be parsed, False otherwise.
        :rtype: bool
        """
        return self.using is not None

    def singleValueFromClient(self, value, skel, bone_name, client_data):
        errors = []

        if isinstance(value, dict):
            dest_key = value.pop("key", None)
        else:
            dest_key = value
            value = {}

        if self.using:
            rel = self.using()
            if not rel.fromClient(value):
                errors.append(
                    ReadFromClientError(
                        ReadFromClientErrorSeverity.Invalid,
                        i18n.translate("core.bones.error.incomplete", "Incomplete data"),
                    )
                )

            errors.extend(rel.errors)
        else:
            rel = None

        # FIXME VIUR4: createRelSkelFromKey doesn't accept an instance of a RelSkel...
        if ret := self.createRelSkelFromKey(dest_key, None):  # ...therefore we need to first give None...
            ret["rel"] = rel  # ...and then assign it manually.

            if err := self.isInvalid(ret):
                ret = self.getEmptyValue()
                errors.append(ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err))

            return ret, errors

        elif self.consistency == RelationalConsistency.Ignore:
            # when RelationalConsistency.Ignore is on, keep existing relations, even when they where deleted
            for _, _, value in self.iter_bone_value(skel, bone_name):
                if str(value["dest"]["key"]) == str(dest_key):
                    value["rel"] = rel
                    return value, errors

        errors.append(ReadFromClientError(ReadFromClientErrorSeverity.Invalid))
        return self.getEmptyValue(), errors

    def _rewriteQuery(self, name, skel, dbFilter, rawFilter):
        """
        Rewrites a datastore query to operate on "viur-relations" instead of the original kind.

        This method is needed to perform relational queries on n:m relations. It takes the original datastore query
        and rewrites it to target the "viur-relations" kind. It also adjusts filters and sort orders accordingly.

        :param str name: The name of the bone.
        :param SkeletonInstance skel: The skeleton instance the bone is a part of.
        :param viur.core.db.Query dbFilter: The original datastore query to be rewritten.
        :param dict rawFilter: The raw filter applied to the original datastore query.

        :return: A tuple containing the name, skeleton, rewritten query, and raw filter.
        :rtype: Tuple[str, 'viur.core.skeleton.SkeletonInstance', 'viur.core.db.Query', dict]

        :raises NotImplementedError: If the original query contains multiple filters with "IN" or "!=" operators.
        :raises RuntimeError: If the filtering is invalid, e.g., using multiple key filters or querying
            properties not in parentKeys.
        """
        origQueries = dbFilter.queries
        if isinstance(origQueries, list):
            raise NotImplementedError(
                "Doing a relational Query with multiple=True and \"IN or !=\"-filters is currently unsupported!")
        dbFilter.queries = db.QueryDefinition("viur-relations", {
            "viur_src_kind =": skel.kindName,
            "viur_dest_kind =": self.kind,
            "viur_src_property =": name

        }, orders=[], startCursor=origQueries.startCursor, endCursor=origQueries.endCursor)
        for k, v in origQueries.filters.items():  # Merge old filters in
            # Ensure that all non-relational-filters are in parentKeys
            if k == db.KEY_SPECIAL_PROPERTY:
                # We must process the key-property separately as its meaning changes as we change the datastore kind were querying
                if isinstance(v, list) or isinstance(v, tuple):
                    logging.warning(f"Invalid filtering! Doing an relational Query on {name} with multiple key= "
                                    f"filters is unsupported!")
                    raise RuntimeError()
                if not isinstance(v, db.Key):
                    v = db.Key(v)
                dbFilter.ancestor(v)
                continue
            boneName = k.split(".")[0].split(" ")[0]
            if boneName not in self.parentKeys and boneName != "__key__":
                logging.warning(f"Invalid filtering! {boneName} is not in parentKeys of RelationalBone {name}!")
                raise RuntimeError()
            dbFilter.filter(f"src.{k}", v)
        orderList = []
        for k, d in origQueries.orders:  # Merge old sort orders in
            if k == db.KEY_SPECIAL_PROPERTY:
                orderList.append((f"{k}", d))
            elif not k in self.parentKeys:
                logging.warning(f"Invalid filtering! {k} is not in parentKeys of RelationalBone {name}!")
                raise RuntimeError()
            else:
                orderList.append((f"src.{k}", d))
        if orderList:
            dbFilter.order(*orderList)
        return name, skel, dbFilter, rawFilter

    def buildDBFilter(
        self,
        name: str,
        skel: "SkeletonInstance",
        dbFilter: db.Query,
        rawFilter: dict,
        prefix: t.Optional[str] = None
    ) -> db.Query:
        """
        Builds a datastore query by modifying the given filter based on the RelationalBone's properties.

        This method takes a datastore query and modifies it according to the relational bone properties.
        It also merges any related filters based on the 'refKeys' and 'using' attributes of the bone.

        :param str name: The name of the bone.
        :param SkeletonInstance skel: The skeleton instance the bone is a part of.
        :param db.Query dbFilter: The original datastore query to be modified.
        :param dict rawFilter: The raw filter applied to the original datastore query.
        :param str prefix: Optional prefix to be applied to filter keys.

        :return: The modified datastore query.
        :rtype: db.Query

        :raises RuntimeError: If the filtering is invalid, e.g., querying properties not in 'refKeys'
                          or not a bone in 'using'.
        """
        relSkel, _usingSkelCache = self._getSkels()
        origQueries = dbFilter.queries

        if origQueries is None:  # This query is unsatisfiable
            return dbFilter

        myKeys = [x for x in rawFilter.keys() if x.startswith(f"{name}.")]
        if len(myKeys) > 0:  # We filter by some properties
            if dbFilter.getKind() != "viur-relations" and self.multiple:
                name, skel, dbFilter, rawFilter = self._rewriteQuery(name, skel, dbFilter, rawFilter)

            # Merge the relational filters in
            for myKey in myKeys:
                value = rawFilter[myKey]

                try:
                    unused, _type, key = myKey.split(".", 2)
                    assert _type in ["dest", "rel"]
                except:
                    if self.using is None:
                        # This will be a "dest" query
                        _type = "dest"
                        try:
                            unused, key = myKey.split(".", 1)
                        except:
                            continue
                    else:
                        continue

                # just use the first part of "key" to check against our refSkel / relSkel (strip any leading .something and $something)
                checkKey = key
                if "." in checkKey:
                    checkKey = checkKey.split(".")[0]

                if "$" in checkKey:
                    checkKey = checkKey.split("$")[0]

                if _type == "dest":

                    # Ensure that the relational-filter is in refKeys
                    if checkKey not in self._ref_keys:
                        logging.warning(f"Invalid filtering! {key} is not in refKeys of RelationalBone {name}!")
                        raise RuntimeError()

                    # Iterate our relSkel and let these bones write their filters in
                    for bname, bone in relSkel.items():
                        if checkKey == bname:
                            newFilter = {key: value}
                            if self.multiple:
                                bone.buildDBFilter(bname, relSkel, dbFilter, newFilter, prefix=(prefix or "") + "dest.")
                            else:
                                bone.buildDBFilter(bname, relSkel, dbFilter, newFilter,
                                                   prefix=(prefix or "") + name + ".dest.")

                elif _type == "rel":

                    # Ensure that the relational-filter is in refKeys
                    if self.using is None or checkKey not in self.using():
                        logging.warning(f"Invalid filtering! {key} is not a bone in 'using' of {name}")
                        raise RuntimeError()

                    # Iterate our usingSkel and let these bones write their filters in
                    for bname, bone in self.using().items():
                        if key.startswith(bname):
                            newFilter = {key: value}
                            if self.multiple:
                                bone.buildDBFilter(bname, relSkel, dbFilter, newFilter, prefix=(prefix or "") + "rel.")
                            else:
                                bone.buildDBFilter(bname, relSkel, dbFilter, newFilter,
                                                   prefix=(prefix or "") + name + ".rel.")

            if self.multiple:
                dbFilter.setFilterHook(lambda s, filter, value: self.filterHook(name, s, filter, value))
                dbFilter.setOrderHook(lambda s, orderings: self.orderHook(name, s, orderings))

        elif name in rawFilter and isinstance(rawFilter[name], str) and rawFilter[name].lower() == "none":
            dbFilter = dbFilter.filter(f"{name} =", None)

        return dbFilter

    def buildDBSort(
        self,
        name: str,
        skel: "SkeletonInstance",
        query: db.Query,
        params: dict,
        postfix: str = "",
    ) -> t.Optional[db.Query]:
        """
        Builds a datastore query by modifying the given filter based on the RelationalBone's properties for sorting.

        This method takes a datastore query and modifies its sorting behavior according to the relational bone
        properties. It also checks if the sorting is valid based on the 'refKeys' and 'using' attributes of the bone.

        :param name: The name of the bone.
        :param skel: The skeleton instance the bone is a part of.
        :param query: The original datastore query to be modified.
        :param params: The raw filter applied to the original datastore query.

        :return: The modified datastore query with updated sorting behavior.
        :rtype: t.Optional[db.Query]

        :raises RuntimeError: If the sorting is invalid, e.g., using properties not in 'refKeys'
            or not a bone in 'using'.
        """
        if query.queries and (orderby := params.get("orderby")) and utils.string.is_prefix(orderby, name):
            if self.multiple and query.getKind() != "viur-relations":
                # This query has not been rewritten (yet)
                name, skel, query, params = self._rewriteQuery(name, skel, query, params)

            try:
                _, _type, param = orderby.split(".")
            except ValueError as e:
                logging.exception(f"Invalid layout of {orderby=}: {e}")
                return query
            if _type not in ("dest", "rel"):
                logging.error("Invalid type {_type}")
                return query

            # Ensure that the relational-filter is in refKeys
            if _type == "dest" and param not in self._ref_keys:
                raise RuntimeError(f"Invalid filtering! {param!r} is not in refKeys of RelationalBone {name!r}!")
            elif _type == "rel" and (self.using is None or param not in self.using()):
                raise RuntimeError(f"Invalid filtering! {param!r} is not a bone in 'using' of RelationalBone {name!r}")

            if self.multiple:
                path = f"{_type}.{param}"
            else:
                path = f"{name}.{_type}.{param}"

            order = utils.parse.sortorder(params.get("orderdir"))
            query = query.order((path, order))

            if self.multiple:
                query.setFilterHook(lambda s, query, value: self.filterHook(name, s, query, value))
                query.setOrderHook(lambda s, orderings: self.orderHook(name, s, orderings))

        return query

    def filterHook(self, name, query, param, value):  # FIXME
        """
        Hook installed by buildDbFilter that rewrites filters added to the query to match the layout of the
        viur-relations index and performs sanity checks on the query.

        This method rewrites and validates filters added to a datastore query after the `buildDbFilter` method
        has been executed. It ensures that the filters are compatible with the structure of the viur-relations
        index and checks if the query is possible.

        :param str name: The name of the bone.
        :param db.Query query: The datastore query to be modified.
        :param str param: The filter parameter to be checked and potentially modified.
        :param value: The value associated with the filter parameter.

        :return: A tuple containing the modified filter parameter and its associated value, or None if
             the filter parameter is a key special property.
        :rtype: Tuple[str, Any] or None

        :raises RuntimeError: If the filtering is invalid, e.g., using properties not in 'refKeys' or 'parentKeys'.
        """
        if param.startswith("src.") or param.startswith("dest.") or param.startswith("viur_"):
            # This filter is already valid in our relation
            return param, value
        if param.startswith(f"{name}."):
            # We add a constrain filtering by properties of the referenced entity
            refKey = param.replace(f"{name}.", "")
            if " " in refKey:  # Strip >, < or = params
                refKey = refKey[:refKey.find(" ")]
            if refKey not in self._ref_keys:
                logging.warning(f"Invalid filtering! {refKey} is not in refKeys of RelationalBone {name}!")
                raise RuntimeError()
            if self.multiple:
                return param.replace(f"{name}.", "dest."), value
            else:
                return param, value
        else:
            # We filter by a property of this entity
            if not self.multiple:
                # Not relational, not multiple - nothing to do here
                return param, value
            # Prepend "src."
            srcKey = param
            if " " in srcKey:
                srcKey = srcKey[: srcKey.find(" ")]  # Cut <, >, and =
            if srcKey == db.KEY_SPECIAL_PROPERTY:  # Rewrite key= filter as its meaning has changed
                if isinstance(value, list) or isinstance(value, tuple):
                    logging.warning(f"Invalid filtering! Doing an relational Query on {name} "
                                    f"with multiple key= filters is unsupported!")
                    raise RuntimeError()
                if not isinstance(value, db.Key):
                    value = db.Key(value)
                query.ancestor(value)
                return None
            if srcKey not in self.parentKeys:
                logging.warning(f"Invalid filtering! {srcKey} is not in parentKeys of RelationalBone {name}!")
                raise RuntimeError()
            return f"src.{param}", value

    def orderHook(self, name: str, query: db.Query, orderings):  # FIXME
        """
        Hook installed by buildDbFilter that rewrites orderings added to the query to match the layout of the
        viur-relations index and performs sanity checks on the query.

        This method rewrites and validates orderings added to a datastore query after the `buildDbFilter` method
        has been executed. It ensures that the orderings are compatible with the structure of the viur-relations
        index and checks if the query is possible.

        :param name: The name of the bone.
        :param query: The datastore query to be modified.
        :param orderings: A list or tuple of orderings to be checked and potentially modified.
        :type orderings: List[Union[str, Tuple[str, db.SortOrder]]] or Tuple[Union[str, Tuple[str, db.SortOrder]]]

        :return: A list of modified orderings that are compatible with the viur-relations index.
        :rtype: List[Union[str, Tuple[str, db.SortOrder]]]

        :raises RuntimeError: If the ordering is invalid, e.g., using properties not in 'refKeys' or 'parentKeys'.
        """
        res = []
        if not isinstance(orderings, list) and not isinstance(orderings, tuple):
            orderings = [orderings]
        for order in orderings:
            if isinstance(order, tuple):
                orderKey = order[0]
            else:
                orderKey = order
            if orderKey.startswith("dest.") or orderKey.startswith("rel.") or orderKey.startswith("src."):
                # This is already valid for our relational index
                res.append(order)
                continue
            if orderKey.startswith(f"{name}."):
                k = orderKey.replace(f"{name}.", "")
                if k not in self._ref_keys:
                    logging.warning(f"Invalid ordering! {k} is not in refKeys of RelationalBone {name}!")
                    raise RuntimeError()
                if not self.multiple:
                    res.append(order)
                else:
                    if isinstance(order, tuple):
                        res.append((f"dest.{k}", order[1]))
                    else:
                        res.append(f"dest.{k}")
            else:
                if not self.multiple:
                    # Nothing to do here
                    res.append(order)
                    continue
                else:
                    if orderKey not in self.parentKeys:
                        logging.warning(
                            f"Invalid ordering! {orderKey} is not in parentKeys of RelationalBone {name}!")
                        raise RuntimeError()
                    if isinstance(order, tuple):
                        res.append((f"src.{orderKey}", order[1]))
                    else:
                        res.append(f"src.{orderKey}")
        return res

    def refresh(self, skel: "SkeletonInstance", name: str) -> None:
        """
        Refreshes all values that might be cached from other entities in the provided skeleton.

        This method updates the cached values for relational bones in the provided skeleton, which
        correspond to other entities. It fetches the updated values for the relational bone's
        reference keys and replaces the cached values in the skeleton with the fetched values.

        :param SkeletonInstance skel: The skeleton containing the bone to be refreshed.
        :param str boneName: The name of the bone to be refreshed.
        """
        if not skel[name] or self.updateLevel == RelationalUpdateLevel.OnValueAssignment:
            return

        for _, _, value in self.iter_bone_value(skel, name):
            if value and value["dest"]:
                try:
                    target_skel = value["dest"].read()
                except ValueError:

                    # Handle removed reference according to the RelationalConsistency settings
                    match self.consistency:
                        case RelationalConsistency.CascadeDeletion:
                            logging.info(
                                f"{name}: "
                                f"Cascade deleting {skel["key"]!r} ({skel["name"]!r}) "
                                f"due removal of relation {value["dest"]["key"]!r} ({value["dest"]["name"]!r})"
                            )
                            skel._cascade_deletion = True
                            break

                        case RelationalConsistency.SetNull:
                            logging.info(
                                f"{name}: "
                                f"Emptying relation {skel["key"]!r} ({skel["name"]!r}) "
                                f"due removal of {value["dest"]["key"]!r} ({value["dest"]["name"]!r})"
                            )
                            value.clear()

                        case _:
                            logging.info(
                                f"{name}: "
                                f"Relation from {skel["key"]!r} ({skel["name"]!r}) "
                                f"refers to deleted {value["dest"]["key"]!r} ({value["dest"]["name"]!r}), skipping"
                            )

                    continue

                # Copy over the refKey values
                for key in self.refKeys:
                    value["dest"][key] = target_skel[key]

    def getSearchTags(self, skel: "SkeletonInstance", name: str) -> set[str]:
        """
        Retrieves the search tags for the given RelationalBone in the provided skeleton.

        This method iterates over the values of the relational bone and gathers search tags from the
        reference and using skeletons. It combines all the tags into a set to avoid duplicates.

        :param skel: The skeleton containing the bone for which search tags are to be retrieved.
        :param name: The name of the bone for which search tags are to be retrieved.

        :return: A set of search tags for the specified relational bone.
        """
        result = set()

        def get_values(skel_, values_cache):
            for key, bone in skel_.items():
                if not bone.searchable:
                    continue
                for tag in bone.getSearchTags(values_cache, key):
                    result.add(tag)

        ref_skel_cache, using_skel_cache = self._getSkels()
        for idx, lang, value in self.iter_bone_value(skel, name):
            if value is None:
                continue
            if value["dest"]:
                get_values(ref_skel_cache, value["dest"])
            if value["rel"]:
                get_values(using_skel_cache, value["rel"])

        return result

    def createRelSkelFromKey(self, key: db.Key, rel: dict | None = None) -> RelDict | None:
        if rel_skel := self.relskels_from_keys([(key, rel)]):
            return rel_skel[0]
        return None

    def relskels_from_keys(self, key_rel_list: list[tuple[db.Key, dict | None]]) -> list[RelDict]:
        """
        Creates a list of RelSkel instances valid for this bone from the given database key.

        This method retrieves the entity corresponding to the provided key from the database, unserializes it
        into a reference skeleton, and returns a dictionary containing the reference skeleton and optional
        relation data.

        :param key_rel_list: List of tuples with the first value in the tuple is the
            key and the second is and RelSkel or None

        :return: A dictionary containing a reference skeleton and optional relation data.
        """

        if not all(db_objs := db.get([db.key_helper(value[0], self.kind, adjust_kind=True) for value in key_rel_list])):
            return []  # return emtpy data when not all data is found

        res_rel_skels = []

        for (key, rel), db_obj in zip(key_rel_list, db_objs):
            dest_skel = self._refSkelCache()
            dest_skel.unserialize(db_obj)
            for bone_name in dest_skel:
                # Unserialize all bones from refKeys, then drop dbEntity - otherwise all properties will be copied
                _ = dest_skel[bone_name]
            dest_skel.dbEntity = None
            res_rel_skels.append(
                {
                    "dest": dest_skel,
                    "rel": rel or None
                }
            )

        return res_rel_skels

    def setBoneValue(
        self,
        skel: "SkeletonInstance",
        boneName: str,
        value: t.Any,
        append: bool,
        language: None | str = None
    ) -> bool:
        """
        Sets the value of the specified bone in the given skeleton. Sanity checks are performed to ensure the
        value is valid. If the value is invalid, no modifications are made.

        :param skel: Dictionary with the current values from the skeleton we belong to.
        :param boneName: The name of the bone to be modified.
        :param value: The value to be assigned. The type depends on the bone type.
        :param append: If true, the given value is appended to the values of the bone instead of replacing it.
            Only supported on bones with multiple=True.
        :param language: Set/append for a specific language (optional). Required if the bone
            supports languages.

        :return: True if the operation succeeded, False otherwise.
        """
        assert not (bool(self.languages) ^ bool(language)), "Language is required or not supported"
        assert not append or self.multiple, "Can't append - bone is not multiple"

        def tuple_check(in_value: tuple | None = None) -> bool:
            """
            Return True if the given value is a tuple with a length of two.
            In addition, the first field in the tuple must be a str,int or db.key.
            Furthermore, the second field must be a skeletonInstanceClassRef.
            """
            return (isinstance(in_value, tuple) and len(in_value) == 2
                        and isinstance(in_value[0], (str, int, db.Key))
                        and isinstance(in_value[1], self._skeletonInstanceClassRef))

        if not self.multiple and not self.using:
            if not isinstance(value, (str, int, db.Key)):
                raise ValueError(f"You must supply exactly one Database-Key str or int to {boneName}")
            parsed_value = (value, None)
        elif not self.multiple and self.using:
            if not tuple_check(value):
                raise ValueError(f"You must supply a tuple of (Database-Key, relSkel) to {boneName}")
            parsed_value = value
        elif self.multiple and not self.using:
            if not isinstance(value, (str, int, db.Key)) and not (isinstance(value, list)) \
                    and all([isinstance(val, (str, int, db.Key)) for val in value]):
                raise ValueError(f"You must supply a Database-Key or a list hereof to {boneName}")
            if isinstance(value, list):
                parsed_value = [(key, None) for key in value]
            else:
                parsed_value = [(value, None)]
        else:  # which means (self.multiple and self.using)
            if not tuple_check(value) and (not isinstance(value, list) or not all(tuple_check(val) for val in value)):
                raise ValueError(f"You must supply (db.Key, RelSkel) or a list hereof to {boneName}")
            if isinstance(value, list):
                parsed_value = value
            else:
                parsed_value = [value]

        if boneName not in skel:
            skel[boneName] = {}
            if language:
                skel[boneName].setdefault(language, [])

        if self.multiple:
            rel_list = self.relskels_from_keys(parsed_value)
            if append:
                if language:
                    skel[boneName][language].extend(rel_list)
                else:
                    if not isinstance(skel[boneName], list):
                        skel[boneName] = []
                    skel[boneName].extend(rel_list)
            else:
                if language:
                    skel[boneName][language] = rel_list
                else:
                    skel[boneName] = rel_list
        else:
            if not (rel := self.createRelSkelFromKey(parsed_value[0], parsed_value[1])):
                return False
            if language:
                skel[boneName][language] = rel
            else:
                skel[boneName] = rel
        return True

    def getReferencedBlobs(self, skel: "SkeletonInstance", name: str) -> set[str]:
        """
        Retrieves the set of referenced blobs from the specified bone in the given skeleton instance.

        :param SkeletonInstance skel: The skeleton instance to extract the referenced blobs from.
        :param str name: The name of the bone to retrieve the referenced blobs from.

        :return: A set containing the unique blob keys referenced by the specified bone.
        :rtype: Set[str]
        """
        result = set()
        for idx, lang, value in self.iter_bone_value(skel, name):
            if value is None:
                continue
            for key, bone_ in value["dest"].items():
                result.update(bone_.getReferencedBlobs(value["dest"], key))
            if value["rel"]:
                for key, bone_ in value["rel"].items():
                    result.update(bone_.getReferencedBlobs(value["rel"], key))
        return result

    def getUniquePropertyIndexValues(self, valuesCache: dict, name: str) -> list[str]:
        """
        Generates unique property index values for the RelationalBone based on the referenced keys.
        Can be overridden if different behavior is required (e.g., examining values from `prop:usingSkel`).

        :param dict valuesCache: The cache containing the current values of the bone.
        :param str name: The name of the bone for which to generate unique property index values.

        :return: A list containing the unique property index values for the specified bone.
        :rtype: List[str]
        """
        value = valuesCache.get(name)
        if not value:  # We don't have a value to lock
            return []
        if isinstance(value, dict):
            return self._hashValueForUniquePropertyIndex(value["dest"]["key"])
        elif isinstance(value, list):
            return self._hashValueForUniquePropertyIndex([x["dest"]["key"] for x in value])

    def structure(self) -> dict:
        return super().structure() | {
            "type": f"{self.type}.{self.kind}",
            "module": self.module,
            "format": self.format,
            "using": self.using().structure() if self.using else None,
            "relskel": self._refSkelCache().structure(),
        }

    def _atomic_dump(self, value: dict[str, "SkeletonInstance"]) -> dict | None:
        if isinstance(value, dict):
            return {
                "dest": value["dest"].dump(),
                "rel": value["rel"].dump() if value["rel"] else None,
            }
