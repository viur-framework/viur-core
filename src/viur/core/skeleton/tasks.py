import logging
import typing as t
import logics

from viur.core import (
    conf,
    current,
    db,
    email,
    errors,
    tasks,
    i18n,
    utils,
)
from .utils import skeletonByKind, listKnownSkeletons
from .meta import BaseSkeleton
from .relskel import RelSkel

from ..bones.raw import RawBone
from ..bones.record import RecordBone
from ..bones.relational import RelationalBone, RelationalConsistency, RelationalUpdateLevel
from ..bones.select import SelectBone
from ..bones.string import StringBone


@tasks.CallDeferred
def processRemovedRelations(removedKey, cursor=None):
    updateListQuery = (
        db.Query("viur-relations")
        .filter("dest.__key__ =", removedKey)
        .filter("viur_relational_consistency >", RelationalConsistency.PreventDeletion.value)
    )
    updateListQuery = updateListQuery.setCursor(cursor)
    updateList = updateListQuery.run(limit=5)

    for entry in updateList:
        skel = skeletonByKind(entry["viur_src_kind"])()

        if not skel.read(entry["src"].key):
            raise ValueError(f"processRemovedRelations detects inconsistency on src={entry['src'].key!r}")

        if entry["viur_relational_consistency"] == RelationalConsistency.SetNull.value:
            found = False

            for key, bone in skel.items():
                if isinstance(bone, RelationalBone):
                    if relational_value := skel[key]:
                        # TODO: LanguageWrapper is not considered here (<RelationalBone(languages=[...])>)
                        if isinstance(relational_value, dict):
                            if relational_value["dest"]["key"] == removedKey:
                                skel[key] = None
                                found = True

                        elif isinstance(relational_value, list):
                            skel[key] = [entry for entry in relational_value if entry["dest"]["key"] != removedKey]
                            found = True

                        else:
                            raise NotImplementedError(f"In {entry['src'].key!r}, no handling for {relational_value=}")

            if found:
                skel.write(update_relations=False)

        else:
            logging.critical(f"""Cascade deletion of {skel["key"]!r}""")
            skel.delete()

    if len(updateList) == 5:
        processRemovedRelations(removedKey, updateListQuery.getCursor())


@tasks.CallDeferred
def updateRelations(
        dest_key: db.Key,
        min_change_time: int,
        changed_bones: t.Optional[t.Iterable[str] | str] = (),
        cursor: t.Optional[str] = None,
        **kwargs
):
    """
        This function updates Entities, which may have a copy of values from another entity which has been recently
        edited (updated). In ViUR, relations are implemented by copying the values from the referenced entity into the
        entity that's referencing them. This allows ViUR to run queries over properties of referenced entities and
        prevents additional db.Get's to these referenced entities if the main entity is read. However, this forces
        us to track changes made to entities as we might have to update these mirrored values.     This is the deferred
        call from meth:`viur.core.skeleton.Skeleton.write()` after an update (edit) on one Entity to do exactly that.

        :param dest_key: The database-key of the entity that has been edited
        :param min_change_time: The timestamp on which the edit occurred. As we run deferred, and the entity might have
            been edited multiple times before we get acutally called, we can ignore entities that have been updated
            in the meantime as they're  already up-to-date
        :param changed_bones: If set, we'll update only entites that have a copy of that bones. Relations mirror only
            key and name by default, so we don't have to update these if only another bone has been changed.
        :param cursor: The database cursor for the current request as we only process five entities at once and then
            defer again.
    """
    changed_bones = list(utils.ensure_iterable(changed_bones))
    if "changedBone" in kwargs:
        logging.warning("Use of `changedBone` is deprecated; Use `changed_bones` instead!", stacklevel=2)
        changed_bones.extend(utils.ensure_iterable(kwargs["changedBone"]))
    if "minChangeTime" in kwargs:
        logging.warning("Use of `minChangeTime` is deprecated; Use `min_cahnge_time` instead!", stacklevel=2)
        min_change_time = kwargs["minChangeTime"]
    if "destKey" in kwargs:
        logging.warning("Use of `destKey` is deprecated; Use `dest_key` instead!", stacklevel=2)
        dest_key = kwargs["destKey"]
    logging.debug(f"Starting updateRelations for {dest_key=}; {min_change_time=}, {changed_bones=}, {cursor=}")
    if request_data := current.request_data.get():
        request_data["__update_relations_bones"] = changed_bones
    update_list_query = (
        db.Query("viur-relations")
        .filter("dest.__key__ =", dest_key)
        .filter("viur_delayed_update_tag <", min_change_time)
        .filter("viur_relational_updateLevel =", RelationalUpdateLevel.Always.value)
    )
    if changed_bones:
        update_list_query.filter("viur_foreign_keys IN", changed_bones)
    if cursor:
        update_list_query.setCursor(cursor)
    update_list = update_list_query.run(limit=5)

    def __txn_update(_skel, key, srcRelKey):
        if not _skel.read(key):
            logging.warning(f"Cannot update stale reference to {key=} (referenced from {srcRelKey=})")
            return

        _skel.refresh()
        _skel.write(update_relations=False)

    for src_rel in update_list:
        try:
            skel = skeletonByKind(src_rel["viur_src_kind"])()
        except AssertionError:
            logging.info(f"""Ignoring {src_rel.key!r} which refers to unknown kind {src_rel["viur_src_kind"]!r}""")
            continue
        if db.is_in_transaction():
            __txn_update(skel, src_rel["src"].key, src_rel.key)
        else:
            db.run_in_transaction(__txn_update, skel, src_rel["src"].key, src_rel.key)
    if len(update_list) == 5 and (next_cursor := update_list_query.getCursor()):
        updateRelations(dest_key, min_change_time, changed_bones, next_cursor)


class SkelIterTask(tasks.QueryIter):
    """
    Iterates the skeletons of a query, and additionally checks a Logics expression.
    When the skeleton is valid, it performs the action `data["action"]` on each entry.
    """

    @classmethod
    def handleEntry(cls, skel, data):
        data["total"] += 1

        if logics.Logics(data["condition"]).run(skel):
            data["count"] += 1

            match data["action"]:
                case "refresh":
                    skel.refresh()
                    skel.write(update_relations=False)

                case "delete":
                    skel.delete()

                case other:
                    assert other == "count"

    @classmethod
    def handleError(cls, skel, data, exception) -> bool:
        logging.exception(exception)

        try:
            logging.debug(f"{skel=!r}")
        except Exception:  # noqa
            logging.warning("Failed to dump skel")
            logging.debug(f"{skel.dbEntity=}")

        data["error"] += 1
        return True

    @classmethod
    def handleFinish(cls, total, data):
        super().handleFinish(total, data)

        if not data["notify"]:
            return

        txt = (
            f"{conf.instance.project_id}: {data["action"]!s} finished for {data['kind']!r}: "
            f"{data['count']} of {data['total']}\n"
            f"ViUR {data["action"]!s}ed {data['count']} skeletons with condition <code>{data["condition"]}</code> on a "
            f"total of {data['total']} ({data["error"]} errored) of kind {data['kind']}.\n"
        )

        try:
            email.send_email(dests=data["notify"], stringTemplate=txt, skel=None)
        except Exception as exc:  # noqa; OverQuota, whatever
            logging.exception(f'Failed to notify {data["notify"]}')


@tasks.CallableTask
class SkeletonMaintenanceTask(tasks.CallableTaskBase):
    key = "SkeletonMaintenanceTask"
    name = "Skeleton Maintenance"
    descr = "Perform filtered maintenance operations on skeletons."

    def canCall(self):
        user = current.user.get()
        return user and "root" in user["access"]

    class dataSkel(RelSkel):
        task = SelectBone(
            descr="Task",
            required=True,
            values={
                "count": "Count",
                "refresh": "Refresh (formerly: RebuildSearchIndex)",
                "delete": "Delete",
            },
            defaultValue="refresh",
        )

        kinds = SelectBone(
            descr="Kind",
            values=listKnownSkeletons,
            required=True,
            multiple=True,
        )

        class FilterRowUsingSkel(RelSkel):
            name = StringBone(
                required=True,
            )

            op = SelectBone(
                required=True,
                values={
                    "$eq": "=",
                    "$lt": "<",
                    "$gt": ">",
                    "$lk": "like",
                },
                defaultValue=" ",
            )

            value = StringBone(
                required=True,
            )

        filters = RecordBone(
            descr="Filter",
            using=FilterRowUsingSkel,
            multiple=True,
            format="$(name)$(op)=$(value)",
        )

        condition = RawBone(
            descr="Condition",
            required=True,
            defaultValue="False  # fused: by default, doesn't affect anything.\n",
            params={
                "tooltip": "Enter a Logics expression here to filter entries by specific skeleton values."
            },
        )

    def execute(self, task, kinds, filters, condition):
        try:
            logics.Logics(condition)
        except logics.ParseException as e:
            raise errors.BadRequest(f"Error parsing condition {e}")

        notify = current.user.get()["name"]

        for kind in kinds:
            q = skeletonByKind(kind)().all()

            for flt in filters:
                q.mergeExternalFilter({(flt["name"] + flt["op"]).rstrip("$eq"): flt["value"]})

            params = {
                "action": task,
                "notify": notify,
                "condition": condition,
                "kind": kind,
                "count": 0,
                "total": 0,
                "error": 0,
            }

            SkelIterTask.startIterOnQuery(q, params)
