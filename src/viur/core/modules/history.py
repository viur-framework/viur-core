import difflib
import json
import logging
import typing as t
from google.cloud import exceptions, bigquery
from viur.core import db, conf, utils, current, tasks
from viur.core.bones import *
from viur.core.prototypes.list import List
from viur.core.render.json.default import CustomJsonEncoder
from viur.core.skeleton import SkeletonInstance, Skeleton, DatabaseAdapter


class HistorySkel(Skeleton):
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
    )

    name = StringBone(
        descr="Name",
        searchable=True,
    )

    descr = StringBone(
        descr="Description",
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

    changed_fields = StringBone(
        descr="Changed fields",
        multiple=True
    )

    diff = RawBone(
        descr="Human-readable diff",
        indexed=False,
    )


class BigQueryHistory:
    """
    Connector for BigQuery history entries.
    """

    PATH = f"""{conf.instance.project_id}.history.default"""
    """
    Path to the big query table for history entries.
    """

    SCHEMA = (
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
        {
            "type": "STRING",
            "name": "changed_fields",
            "mode": "REPEATED",
            "description": "Changed fields from old to new",
        },
    )
    """
    Schema used for the BigQuery table for its initial construction.
    Keep to the provided format!
    """

    def __init__(self):
        super().__init__()

        # checks for the table_path
        if self.PATH.count(".") != 2:
            raise ValueError("{self.PATH!r} must have exactly 3 parts that separated by a dot.")

        self.client = bigquery.Client()
        self.table = self.select_or_create_table()

    def select_or_create_table(self):
        try:
            return self.client.get_table(self.PATH)

        except exceptions.NotFound:
            app, dataset, table = self.PATH.split(".")
            logging.error(f"{app}:{dataset}:{table}")
            # create dataset if needed
            try:
                self.client.get_dataset(dataset)
            except exceptions.NotFound:
                logging.info(f"Dataset {dataset!r} does not exist, creating")
                self.client.create_dataset(dataset)

            # create table if needed
            try:
                return self.client.get_table(self.PATH)
            except exceptions.NotFound:
                logging.info(f"Table {self.PATH!r} does not exist, creating")
                self.client.create_table(
                    bigquery.Table(
                        self.PATH,
                        schema=self.SCHEMA
                    )
                )
                return self.client.get_table(self.PATH)

    def write_row(self, data):
        if res := self.client.insert_rows(self.table, [data]):
            raise ValueError(res)


class HistoryAdapter(DatabaseAdapter):
    """
    Generalized adapter for handling history events.
    """

    DEFAULT_EXCLUDES = {
        "key",
        "changedate",
        "creationdate",
        "importdate",
        "viurCurrentSeoKeys",
    }
    """
    Bones being ignored within history.
    """

    def __init__(self, excludes: t.Iterable[str] = DEFAULT_EXCLUDES):
        super().__init__()

        # add excludes to diff excludes
        self.diff_excludes = set(excludes)

    def prewrite(self, skel, is_add, change_list=()):
        if not is_add:  # edit
            old_skel = skel.clone()
            old_skel.read(skel["key"])
            self.trigger("edit", old_skel, skel, change_list)

    def write(self, skel, is_add, change_list=()):
        if is_add:  # add
            self.trigger("add", None, skel)

    def delete(self, skel):
        self.trigger("delete", skel, None)

    def trigger(
        self,
        action: str,
        old_skel: SkeletonInstance,
        new_skel: SkeletonInstance,
        change_list: t.Iterable[str] = (),
    ) -> str | None:
        if not (history_module := getattr(conf.main_app, "history", None)):
            logging.warning(
                f"{old_skel or new_skel or self!r} uses {self.__class__.__name__}, but no 'history'-module found"
            )
            return None

        # skip excluded actions like login or logout
        if action in conf.history.excluded_actions:
            return None

        # skip when no user is available or provided
        if not (user := current.user.get()):
            return None

        # FIXME: Turn change_list into set, in entire Core...
        if change_list and not set(change_list).difference(self.diff_excludes):
            logging.info("change_list is empty, nothing to write")
            return None

        # skip excluded kinds and history kind to avoid recursion
        any_skel = (old_skel or new_skel)
        if any_skel and (kindname := getattr(any_skel, "kindName", None)):
            if kindname in conf.history.excluded_kinds:
                return None

            if kindname == "viur-history":
                return None

        return history_module.write_diff(
            action, old_skel, new_skel,
            change_list=change_list,
            user=user,
            diff_excludes=self.diff_excludes,
        )


class History(List):
    """
    ViUR history module
    """
    kindName = "viur-history"

    adminInfo = {
        "name": "History",
        "icon": "clock-history",
        "filter": {
            "orderby": "timestamp",
            "orderdir": "desc",
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

    BigQueryHistoryCls = BigQueryHistory
    """
    The connector class used to store entries to BigQuery.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.BigQueryHistoryCls and "bigquery" in conf.history.databases:
            assert issubclass(self.BigQueryHistoryCls, BigQueryHistory)
            self.bigquery = self.BigQueryHistoryCls()
        else:
            self.bigquery = None

    def skel(self, **kwargs):
        # Make all bones readonly!
        skel = super().skel(**kwargs).clone()
        skel.readonly()
        return skel

    def canEdit(self, skel):
        return self.canView(skel)  # this is needed to open an entry in admin (all bones are readonly!)

    def canDelete(self, _skel):
        return False

    def canAdd(self):
        return False

    # Module-specific functions
    @staticmethod
    def _create_diff(new: dict, old: dict, diff_excludes: t.Iterable[str] = set()):
        """
        Creates a textual diff format string from the contents of two dicts.
        """
        diffs = []

        # Run over union of both dict keys
        keys = old.keys() | new.keys()
        keys = set(keys).difference(diff_excludes)
        keys = sorted(keys)

        for key in keys:
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
                    ret[name] = json.dumps(obj, cls=CustomJsonEncoder)

                return ret

            values = tuple(expand((key,), obj.get(key)) for obj in (old, new))
            assert len(values) == 2

            for value_key in sorted(set(values[0].keys() | values[1].keys())):

                diff = "\n".join(
                    difflib.unified_diff(
                        (values[0].get(value_key) or "").splitlines(),
                        (values[1].get(value_key) or "").splitlines(),
                        value_key, value_key,
                        old.get("changedate") or utils.utcNow().isoformat(),
                        new.get("changedate") or utils.utcNow().isoformat(),
                        n=1
                    )
                )

                if diff := diff.strip():
                    diffs.append(diff)

        return "\n".join(diffs).replace("\n\n", "\n")

    def build_name(self, skel: SkeletonInstance) -> str | None:
        """
        Helper function to figure out a name from the skeleton
        """

        if not skel:
            return None

        if "name" in skel:
            name = skel.dump()

            if isinstance(skel["name"], str):
                return skel["name"]

            return name

        return skel["key"].id_or_name

    def build_descr(self, action: str, skel: SkeletonInstance, change_list: t.Iterable[str]) -> str | None:
        """
        Helper function to build a description about the change to the skeleton
        """
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

    def create_history_entry(
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
        """
        Internal helper function that constructs a JSON-serializable form of the entry
        that can either be written to datastore or another database.
        """
        skel = new_skel or old_skel
        new_data = skel.dump()

        if change_list and old_skel != new_skel:
            old_data = old_skel.dump()
            diff = self._create_diff(new_data, old_data, diff_excludes)
        else:
            old_data = {}
            diff = ""

        # set event tag, in case of an event-action
        tags = set(tags)

        # Event tag
        if action.startswith("event-"):
            tags.add("is-event")

        ret = {
            "action": action,
            "current_key": skel and str(skel["key"]),
            "current_kind": skel and getattr(skel, "kindName", None),
            "current": new_data,
            "changed_fields": change_list if change_list else [],
            "descr": descr or self.build_descr(action, skel, change_list),
            "diff": diff,
            "name": self.build_name(skel) if skel else ((user and user["name"] or "") + " " + action),
            "previous": old_data if old_data else None,
            "tags": tuple(sorted(tags)),
            "timestamp": utils.utcNow(),
            "user_firstname": user and user["firstname"],
            "user_lastname": user and user["lastname"],
            "user_name": user and user["name"],
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
        entry = self.create_history_entry(
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
        if "viur" in conf.history.databases:
            self.write_deferred(key, entry)

        # write into BigQuery
        if self.bigquery and "bigquery" in conf.history.databases:
            # need to do this as biquery functions modifies entry and seems to be called first
            if conf.instance.is_dev_server:
                entry = entry.copy()  # need to do this as biquery functions modifiy entry

            self.write_to_bigquery_deferred(key, entry)

        return key

    def write(self, key: str, entry: dict):
        """
        Write a history entry generated from an HistoryAdapter.
        """
        skel = self.addSkel()

        for name, bone in skel.items():
            if value := entry.get(name):
                if isinstance(bone, (RelationalBone, RecordBone)):
                    skel.setBoneValue(name, value)
                else:
                    skel[name] = value

        skel.write(key=db.Key(skel.kindName, key))

        logging.info(f"History entry {key=} written to datastore")

    @tasks.CallDeferred
    def write_deferred(self, key: str, entry: dict):
        self.write(key, entry)

    def write_to_bigquery(self, key: str, entry: dict):
        entry["key"] = key
        entry["timestamp_date"] = entry["timestamp"].strftime("%Y-%m-%d")
        entry["timestamp_period"] = entry["timestamp"].strftime("%Y-%m")
        entry["user"] = str(entry["user"]) if entry["user"] else None

        self.bigquery.write_row(entry)
        logging.info(f"History entry {key=} written to biquery")

    @tasks.CallDeferred
    def write_to_bigquery_deferred(self, key: str, entry: dict):
        self.write_to_bigquery(key, entry)


History.json = True
History.admin = True
