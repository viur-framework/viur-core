import logging
import typing as t
import logics
import time

from viur.core import (
    conf,
    current,
    db,
    email,
    errors,
    tasks,
    utils,
)
from .utils import skeletonByKind, listKnownSkeletons
from .relskel import RelSkel

from ..bones.raw import RawBone
from ..bones.record import RecordBone
from ..bones.relational import RelationalBone, RelationalConsistency, RelationalUpdateLevel
from ..bones.select import SelectBone
from ..bones.string import StringBone


@tasks.CallDeferred
def update_relations(
    key: db.Key,
    *,
    min_change_time: t.Optional[float] = None,
    changed_bones: t.Optional[t.Iterable[str] | str] = (),
    cursor: t.Optional[str] = None,
    total: int = 0,
    **kwargs
):
    """
        This function updates Entities, which may have a copy of values from another entity which has been recently
        edited (updated). In ViUR, relations are implemented by copying the values from the referenced entity into the
        entity that's referencing them. This allows ViUR to run queries over properties of referenced entities and
        prevents additional db.Get's to these referenced entities if the main entity is read. However, this forces
        us to track changes made to entities as we might have to update these mirrored values.     This is the deferred
        call from meth:`viur.core.skeleton.Skeleton.write()` after an update (edit) on one Entity to do exactly that.

        :param key: The database-key of the entity that has been edited
        :param min_change_time: The timestamp on which the edit occurred. As we run deferred, and the entity might have
            been edited multiple times before we get acutally called, we can ignore entities that have been updated
            in the meantime as they're  already up-to-date
        :param changed_bones: If set, we'll update only entites that have a copy of that bones. Relations mirror only
            key and name by default, so we don't have to update these if only another bone has been changed.
        :param cursor: The database cursor for the current request as we only process five entities at once and then
            defer again.
    """
    # TODO: Remove in VIUR4
    for _dep, _new in {
        "changedBone": "changed_bones",
        "minChangeTime": "min_change_time",
        "destKey": "key",
    }.items():
        if _dep in kwargs:
            logging.warning(f"{_dep!r} parameter is deprecated, please use {_new!r} instead",)
            locals()[_new] = kwargs.pop(_dep)

    if min_change_time is None:
        min_change_time = time.time() + 1

    changed_bones = utils.ensure_iterable(changed_bones)

    if not cursor:
        logging.debug(f"update_relations {key=} {min_change_time=} {changed_bones=}")

    if request_data := current.request_data.get():
        request_data["__update_relations_bones"] = changed_bones

    query = db.Query("viur-relations") \
        .filter("dest.__key__ =", key) \
        .filter("viur_delayed_update_tag <", min_change_time) \
        .filter("viur_relational_updateLevel =", RelationalUpdateLevel.Always.value)

    if changed_bones:
        query.filter("viur_foreign_keys IN", changed_bones)

    query.setCursor(cursor)

    for src_rel in query.run():
        try:
            skel = skeletonByKind(src_rel["viur_src_kind"])()
        except AssertionError:
            logging.info(f"""Ignoring {src_rel.key!r} which refers to unknown kind {src_rel["viur_src_kind"]!r}""")
            continue

        if not skel.patch(lambda skel: skel.refresh(), key=src_rel["src"].key, update_relations=False):
            logging.warning(f"Cannot update stale reference to {src_rel["src"].key!r} referenced by {src_rel.key!r}")

        total += 1

    if next_cursor := query.getCursor():
        update_relations(
            key=key,
            min_change_time=min_change_time,
            changed_bones=changed_bones,
            cursor=next_cursor,
            total=total
        )
    else:
        logging.debug(f"update_relations finished with {total=} on {key=} {min_change_time=} {changed_bones=}")


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
                    if skel["key"]:
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
            f"{conf.instance.project_id}: {data['action']!s} finished for {data['kind']!r}: "
            f"{data['count']} of {data['total']}\n"
            f"ViUR {data['action']!s}ed {data['count']} skeletons with condition <code>{data['condition']}</code> on a "
            f"total of {data['total']} ({data['error']} errored) of kind {data['kind']}.\n"
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
