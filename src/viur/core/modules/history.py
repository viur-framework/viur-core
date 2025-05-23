import difflib
import enum
import json
import logging
import typing as t
from viur.core import db, conf, utils, current, tasks
from viur.core.render.json.default import CustomJsonEncoder
from prototypes.skeleton import SkeletonAbstractSkel, SkeletonInstance
from viur.core.prototypes.list import List
from viur.core.bones import *
from bones import *  # overwrites UserBone
from google.cloud import bigquery, exceptions


class ViurHistorySkel(SkeletonAbstractSkel):
    """
    Skeleton used for a ViUR history entry to log any relevant changes
    in other Skeletons.

    The ViurHistorySkel is also used as the base for a biquery logging table,
    see below.
    """

    kindName = "viur-history"
    creationdate = changedate = None

    version = NumericBone(
        descr="Version",
    )

    action = StringBone(
        descr="Action",
    )

    tags = StringBone(
        descr="Tags",
        multiple=True,
    )

    timestamp = DateBone(
        descr="Timestamp",
        defaultValue=lambda *args, **kwargs: utils.utcNow(),
        localize=True,
    )

    user = UserBone(
        updateLevel=RelationalUpdateLevel.OnValueAssignment,
        searchable=True,
        refKeys=[
            "key",
            "name",
            "lastname",
            "firstname"
        ],
    )
    #Why we need this ?
    origin_user = UserBone(
        descr="User take over by",
        updateLevel=RelationalUpdateLevel.OnValueAssignment,
        searchable=True,
        refKeys=[
            "key",
            "name",
            "lastname",
            "firstname",
        ],
    )

    name = StringBone(
        descr="Name",
        searchable=True,
    )

    descr = StringBone(
        descr="Beschreibung",
        searchable=True,
    )

    current_kind = StringBone(
        descr="Entry kind",
        searchable=True,
    )

    current_key = KeyBone(
        descr="Entity key",
    )

    current = JsonBone(
        descr="Entity content",
        indexed=False,
    )

    diff = RawBone(
        descr="Diff",
        indexed=False,
    )


class BigQueryHistory:
    """
    Schema and connector for BigQuery history entries.
    """

    def __init__(self):
        super().__init__()

        self.tablepath = f"""{conf.instance.project_id}.history.default"""
        self.schema = (
            {
                "type": "STRING",
                "name": "key",
                "mode": "REQUIRED",
                "description": "unique identifier, hashed from kindname + timestamp",
            },
            {
                "type": "NUMERIC",
                "name": "version",
                "mode": "REQUIRED",
                "description": "log version",
            },
            {
                "type": "STRING",
                "name": "action",
                "mode": "NULLABLE",
                "description": "logged action",
            },
            {
                "type": "STRING",
                "name": "tags",
                "mode": "REPEATED",
                "description": "Additional tags for filtering",
            },
            {
                "type": "DATETIME",
                "name": "timestamp",
                "mode": "REQUIRED",
                "description": "datetime of logevent",
            },
            {
                "type": "STRING",
                "name": "timestamp_date",
                "mode": "REQUIRED",
                "description": "datetime of logevent: date",
            },
            {
                "type": "STRING",
                "name": "timestamp_period",
                "mode": "REQUIRED",
                "description": "datetime of logevent: period",
            },
            {
                "type": "STRING",
                "name": "user",
                "mode": "NULLABLE",
                "description": "user who trigged log event: key",
            },
            {
                "type": "STRING",
                "name": "user_name",
                "mode": "NULLABLE",
                "description": "user who trigged log event: username",
            },
            {
                "type": "STRING",
                "name": "user_firstname",
                "mode": "NULLABLE",
                "description": "user who trigged log event: firstname",
            },
            {
                "type": "STRING",
                "name": "user_lastname",
                "mode": "NULLABLE",
                "description": "user who trigged log event: lastname",
            },
            {
                "type": "STRING",
                "name": "user_personnelnumber",
                "mode": "NULLABLE",
                "description": "user who trigged log event: personnelnumber",
            },
            {
                "type": "DATE",
                "name": "user_last_audit",
                "mode": "NULLABLE",
                "description": "user who trigged log event: last audit",
            },
            {
                "type": "STRING",
                "name": "user_company",
                "mode": "NULLABLE",
                "description": "user who trigged log event: company",
            },
            {
                "type": "STRING",
                "name": "origin_user",
                "mode": "NULLABLE",
                "description": "original user who trigged log event: key",
            },
            {
                "type": "STRING",
                "name": "origin_user_name",
                "mode": "NULLABLE",
                "description": "original user who trigged log event: username",
            },
            {
                "type": "STRING",
                "name": "origin_user_firstname",
                "mode": "NULLABLE",
                "description": "original user who trigged log event: firstname",
            },
            {
                "type": "STRING",
                "name": "origin_user_lastname",
                "mode": "NULLABLE",
                "description": "original user who trigged log event: lastname",
            },
            {
                "type": "STRING",
                "name": "origin_user_personnelnumber",
                "mode": "NULLABLE",
                "description": "original user who trigged log event: personnelnumber",
            },
            {
                "type": "DATE",
                "name": "origin_user_last_audit",
                "mode": "NULLABLE",
                "description": "original user who trigged log event: last audit",
            },
            {
                "type": "STRING",
                "name": "origin_user_company",
                "mode": "NULLABLE",
                "description": "original user who trigged log event: company",
            },
            {
                "type": "STRING",
                "name": "name",
                "mode": "NULLABLE",
                "description": "readable name of the action",
            },
            {
                "type": "STRING",
                "name": "descr",
                "mode": "NULLABLE",
                "description": "readable event description",
            },
            {
                "type": "STRING",
                "name": "current_kind",
                "mode": "NULLABLE",
                "description": "kindname",
            },
            {
                "type": "STRING",
                "name": "current_key",
                "mode": "NULLABLE",
                "description": "url encoded datastore key",
            },
            {
                "type": "JSON",
                "name": "current",
                "mode": "NULLABLE",
                "description": "full content of the current entry",
            },
            {
                "type": "JSON",
                "name": "previous",
                "mode": "NULLABLE",
                "description": "previous full content of the entry before it changed",
            },
            {
                "type": "STRING",
                "name": "diff",
                "mode": "NULLABLE",
                "description": "diff data",
            },
        )

        self.client = bigquery.Client()
        self.select_or_create_table()

    def select_or_create_table(self):
        try:
            self.table = self.client.get_table(self.tablepath)

        except exceptions.NotFound:
            app, dataset, table = self.tablepath.split(".")

            # create dataset if needed
            try:
                self.client.get_dataset(dataset)
            except exceptions.NotFound:
                logging.info(f"Dataset {dataset!r} does not exist, creating")
                self.client.create_dataset(dataset)

            # create table if needed
            try:
                self.table = self.client.get_table(self.tablepath)
            except exceptions.NotFound:
                logging.info(f"Table {self.tablepath!r} does not exist, creating")
                self.client.create_table(
                    bigquery.Table(
                        self.tablepath,
                        schema=self.schema
                    )
                )
                self.table = self.client.get_table(self.tablepath)

        logging.debug(f"found bigquery table {self.table!r}")
        return self.table

    def write_row(self, data):
        assert self.client and self.table
        if res := self.client.insert_rows(self.table, [data]):
            raise ValueError(res)

    # ---------------------------------------------------------------------------------------------
    # FIXME: Started below code previously which generates the schema from the ViurHistorySkel
    # This is for now abandoned, but the code should not be thrown away, it could be useful.

    IGNORE_BONES = (
        "viurCurrentSeoKeys",
    )

    # def __init__(self):
    #     super().__init__()
    #     self.client = bigquery.Client()
    #     self.table = None
    #     self.schema = None
    #     self.path = f"""{conf.instance.project_id}.history.default"""

    def __generate_schema(self, skel):
        # FIXME: Currently not in use!
        assert self.schema is None
        self.schema = []

        for name, bone in skel.items():
            if name in self.IGNORE_BONES:
                continue

            def bone_to_schema(name, bone, descr=None):
                if isinstance(bone, RelationalBone):
                    return [
                        bone_to_schema(
                            f"{name}_{relname}",
                            relbone,
                            descr=f"""{(descr or "") + bone.descr} - {relbone.descr}"""
                        )
                        for relname, relbone in bone._refSkelCache().items()
                    ]
                elif isinstance(bone, BooleanBone):
                    datatype = "BOOLEAN"
                elif isinstance(bone, JsonBone):
                    datatype = "JSON"
                elif isinstance(bone, DateBone):
                    datatype = "DATETIME"
                elif isinstance(bone, NumericBone):
                    datatype = "NUMERIC"
                elif isinstance(bone, RawBone):
                    datatype = "BYTES"
                else:
                    datatype = "STRING"

                return {
                    "type": datatype,
                    "name": name,
                    "mode": "REPEATED" if bone.multiple else "REQUIRED" if bone.required else "NULLABLE",
                    "description": descr or bone.descr,
                }

            schema = bone_to_schema(name, bone)

            if isinstance(schema, dict):
                self.schema.append(schema)
            else:
                self.schema.extend(schema)

    def _get_table(self, skel):
        # FIXME: Currently not in use!
        if self.table:
            return self.table

        try:
            self.table = self.client.get_table(self.path)

        except exceptions.NotFound:
            app, dataset, table = self.path.split(".")

            self.__generate_schema()

            # create dataset if needed
            try:
                self.client.get_dataset(dataset)
            except exceptions.NotFound:
                self.client.create_dataset(dataset)

            # create table if needed
            try:
                self.table = self.client.get_table(self.path)
            except exceptions.NotFound:
                self.table = bigquery.Table(
                    self.path,
                    schema=self.schema
                )
                self.client.create_table(table)

        return self.table

    def write_skel(self, skel):
        # FIXME: Currently not in use!
        self._get_table(skel)

        def skel_to_bigquery(skel, prefix="") -> dict:
            values = {}

            for name, bone in skel.items():
                if name in self.IGNORE_BONES:
                    continue

                if isinstance(bone, RelationalBone):
                    values |= skel_to_bigquery(skel[name], prefix + name + "_")
                else:
                    values[prefix + name] = skel[name]

            return values

        return self.client.insert_rows(self.table, [skel_to_bigquery(skel)])


class ViurHistory(List):
    """
    ViUR history module
    """
    kindName = "viur-history"

    adminInfo = {
        "name": "Protokoll",
        "icon": "clock-history",
        "filter": {
            "orderby": "timestamp",
            "orderdir": "1",
        },
        "disabledActions": ["add", "clone", "delete"],
    }

    roles = {
        "admin": "view",
    }

    HISTORY_VERSION = 1
    """
    History format version.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bigquery = BigQueryHistory()

    def baseSkel(self):
        # Make all bones readOnly!
        # FIXME: There should be a skel.readonly() function soon...
        skel = super().baseSkel().clone()

        for bone in skel.values():
            bone.readOnly = True

        return skel

    def canEdit(self, skel):
        return self.canView(skel)

    def canDelete(self, _skel):
        return False

    def canAdd(self):
        return False

    # Module-specific functions

    def _create_diff(self, new: dict, old: dict, diff_excludes: set[str] = set()):
        """
        Creates a textual diff format string from the contents of two dicts.
        """
        diffs = []

        # Run over union of both dict keys
        for key in sorted(set(old.keys()) | set(new.keys())):
            if key in diff_excludes:
                continue

            def expand(name, obj):
                ret = {}
                if isinstance(obj, list):
                    for i, val in enumerate(obj):
                        ret.update(expand(name + (str(i),), val))
                elif isinstance(obj, dict):
                    for key, val in obj.items():
                        ret.update(expand(name + (str(key),), val))
                else:
                    name = ".".join(name)

                    if obj is None:
                        ret[name] = ""
                    elif isinstance(obj, str):
                        ret[name] = obj
                    elif isinstance(obj, bytes):
                        ret[name] = obj.decode()
                    elif isinstance(obj, enum.Enum):
                        ret[name] = str(obj.value)
                    else:
                        ret[name] = utils.json.dumps(
                            obj,
                            indent=4,
                            sort_keys=True,
                        )

                return ret

            values = tuple(expand((key,), obj.get(key)) for obj in (old, new))
            assert len(values) == 2

            for value_key in sorted(set(list(values[0].keys()) + list(values[1].keys()))):
                diff = "\n".join(
                    difflib.unified_diff(
                        (values[0].get(value_key) or "").splitlines(),
                        (values[1].get(value_key) or "").splitlines(),
                        value_key, value_key,
                        (old.get("changedate") or utils.utcNow()).isoformat(),
                        (new.get("changedate") or utils.utcNow()).isoformat(),
                        n=1
                    )
                )

                if diff := diff.strip():
                    diffs.append(diff)

        return "\n".join(diffs).replace("\n\n", "\n")

    def _skel_to_dict(self, skel):
        # FIXME: This is urine it its purest refinement.
        return conf.main_app.viur_history.render.renderSkelValues(skel) if skel else {}

    def _create_history_entry(
        self,
        action: str,
        old_skel: SkeletonInstance,
        new_skel: SkeletonInstance,
        change_list: t.Iterable[str] = (),
        descr: t.Optional[str] = None,
        user: t.Optional[SkeletonInstance] = None,
        tags: t.Iterable[str] = (),
        diff_excludes: t.Set[str] = set(),
    ):
        skel = new_skel or old_skel
        new = self._skel_to_dict(skel)

        if change_list and old_skel != new_skel:
            old = self._skel_to_dict(old_skel)
            diff = self._create_diff(new, old, diff_excludes)
        else:
            old = {}
            diff = ""

        # Helper function to figure out a name from the skeleton
        def build_name(skel):
            if not skel:
                return str(skel)

            if "name" in skel:
                if isinstance(skel["name"], str):
                    return skel["name"]

                return json.dumps(
                    skel["name"],
                    cls=CustomJsonEncoder,
                    indent=4,
                    sort_keys=True
                )

            return skel["key"].id_or_name

        # Helper function to build a description about the change to the skeleton
        def build_descr(action, skel, change_list):
            if not skel:
                return action

            match action:
                case "add":
                    return (
                        f"""A new entry with the kind {skel.kindName!r}"""
                        f""" and the key {skel["key"].id_or_name!r} was created."""
                    )
                case "edit":
                    return (
                        f"""The entry {skel["key"].id_or_name!r} of kind {skel.kindName!r} has been modified."""
                        f""" The following fields where changed: {", ".join(change_list)}."""
                    )
                case "delete":
                    return f"""The entry {skel["key"].id_or_name!r} of kind {skel.kindName!r} has been deleted."""

            return (
                f"""The action {action!r} resulted in a change to the entry {skel["key"].id_or_name!r}"""
                f""" of kind {skel.kindName!r}."""
            )

        # If viur_origin_user is set in current session, load it as well
        if origin_user := current.session.get().get("viur_origin_user"):
            origin_user_skel = user.clone()
            origin_user_skel.read(origin_user.key)
            origin_user = origin_user_skel

        # set event tag, in case of an event-action
        tags = set(tags)

        if action.startswith("event-"):
            tags.add("is-event")

        ret = {
            "action": action,
            "current_key": skel and str(skel["key"]),
            "current_kind": skel and getattr(skel, "kindName", None),
            "current": json.dumps(new, cls=CustomJsonEncoder, indent=4, sort_keys=True) if new else None,
            "descr": descr or build_descr(action, skel, change_list),
            "diff": diff,
            "name": build_name(skel) if skel else ((user and user["name"] or "") + " " + action),
            "origin_user_firstname": origin_user and origin_user["firstname"],
            "origin_user_last_audit": origin_user and origin_user["last_audit"],
            "origin_user_lastname": origin_user and origin_user["lastname"],
            "origin_user_name": origin_user and origin_user["name"],
            "origin_user_personnelnumber": origin_user and origin_user["personnelnumber"],
            "origin_user_company": origin_user and origin_user["company"],
            "origin_user": origin_user and origin_user["key"],
            "previous": json.dumps(old, cls=CustomJsonEncoder, indent=4, sort_keys=True) if old else None,
            "tags": tuple(sorted(tags)),
            "timestamp": utils.utcNow(),
            "user_firstname": user and user["firstname"],
            "user_last_audit": user and user["last_audit"],
            "user_lastname": user and user["lastname"],
            "user_name": user and user["name"],
            "user_personnelnumber": user and user["personnelnumber"],
            "user_company": user and user["company"],
            "user": user and user["key"],
            "version": self.HISTORY_VERSION,
        }

        return ret

    def write_diff(
        self,
        action: str,
        old_skel: SkeletonInstance = None,
        new_skel: SkeletonInstance = None,
        change_list: t.Iterable[str] = (),
        descr: t.Optional[str] = None,
        user: t.Optional[SkeletonInstance] = None,
        tags: t.Iterable[str] = (),
        diff_excludes: t.Set[str] = set(),
    ) -> str | None:

        # create entry
        entry = self._create_history_entry(
            action, old_skel, new_skel,
            change_list=change_list,
            descr=descr,
            user=user,
            tags=tags,
            diff_excludes=diff_excludes,
        )

        # generate key from significant properties
        key = "-".join(
            part for part in (
                entry["action"],
                entry["current_kind"],
                entry["timestamp"].isoformat()
            ) if part
        )

        # write into datastore via history module
        if "viur" in conf.get("viur.history.database"):
            self.write_deferred(key, entry)

        # write into BigQuery
        if "bigquery" in conf.get("viur.history.database"):
            # need to do this as biquery functions modifies
            # entry and seems to be called first
            if conf.instance.is_dev_server:
                entry = entry.copy()  # need to do this as biquery functions modifiy entry

            conf.main_app.viur_history.write_to_bigquery_deferred(key, entry)

        return key

    def write(self, key: str, entry: dict, deferred: bool = False):
        """
        Write a history entry generated from an HistoryAdapter.
        """
        skel = self.addSkel()

        # FIXME: This is ugly murks. Please fix in a later version.
        for k in skel.keys():
            if value := entry.get(k):
                skel.setBoneValue(k, value)

        skel["key"] = db.Key(skel.kindName, key)
        skel.write()

        logging.info(f"History entry {key=} written to datastore {deferred=}")

    @tasks.CallDeferred
    def write_deferred(self, key: str, entry: dict):
        self.write(key, entry, deferred=True)

    def write_to_bigquery(self, key: str, entry: dict, deferred: bool = False):
        entry["key"] = key
        entry["timestamp_date"] = entry["timestamp"].strftime("%Y-%m-%d")
        entry["timestamp_period"] = entry["timestamp"].strftime("%Y-%m")
        entry["user"] = str(entry["user"]) if entry["user"] else None
        entry["origin_user"] = str(entry["origin_user"]) if entry["origin_user"] else None

        # FIXME: last_audit needs a date, not a datetime.
        entry["user_last_audit"] = entry["user_last_audit"] and entry["user_last_audit"].date()
        entry["origin_user_last_audit"] = entry["origin_user_last_audit"] and entry["origin_user_last_audit"].date()

        self.bigquery.write_row(entry)
        logging.info(f"History entry {key=} written to biquery {deferred=}")

    @tasks.CallDeferred
    def write_to_bigquery_deferred(self, key: str, entry: dict):
        self.write_to_bigquery(key, entry, deferred=True)


ViurHistory.html = False
ViurHistory.json = False
ViurHistory.admin = False
