import logging
import typing as t

from viur.core import conf, current, db, email, translate
from .utils import skeletonByKind, listKnownSkeletons
from .meta import BaseSkeleton

from ..bones.relational import RelationalBone, RelationalConsistency, RelationalUpdateLevel
from ..bones.select import SelectBone

from viur.core.tasks import CallDeferred, CallableTask, CallableTaskBase, QueryIter


@CallDeferred
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


@CallDeferred
def updateRelations(destKey: db.Key, minChangeTime: int, changedBone: t.Optional[str], cursor: t.Optional[str] = None):
    """
        This function updates Entities, which may have a copy of values from another entity which has been recently
        edited (updated). In ViUR, relations are implemented by copying the values from the referenced entity into the
        entity that's referencing them. This allows ViUR to run queries over properties of referenced entities and
        prevents additional db.Get's to these referenced entities if the main entity is read. However, this forces
        us to track changes made to entities as we might have to update these mirrored values.     This is the deferred
        call from meth:`viur.core.skeleton.Skeleton.write()` after an update (edit) on one Entity to do exactly that.

        :param destKey: The database-key of the entity that has been edited
        :param minChangeTime: The timestamp on which the edit occurred. As we run deferred, and the entity might have
            been edited multiple times before we get acutally called, we can ignore entities that have been updated
            in the meantime as they're  already up2date
        :param changedBone: If set, we'll update only entites that have a copy of that bone. Relations mirror only
            key and name by default, so we don't have to update these if only another bone has been changed.
        :param cursor: The database cursor for the current request as we only process five entities at once and then
            defer again.
    """
    logging.debug(f"Starting updateRelations for {destKey=}; {minChangeTime=}, {changedBone=}, {cursor=}")
    if request_data := current.request_data.get():
        request_data["__update_relations_bone"] = changedBone
    updateListQuery = (
        db.Query("viur-relations")
        .filter("dest.__key__ =", destKey)
        .filter("viur_delayed_update_tag <", minChangeTime)
        .filter("viur_relational_updateLevel =", RelationalUpdateLevel.Always.value)
    )
    if changedBone:
        updateListQuery.filter("viur_foreign_keys =", changedBone)
    if cursor:
        updateListQuery.setCursor(cursor)
    updateList = updateListQuery.run(limit=5)

    def updateTxn(skel, key, srcRelKey):
        if not skel.read(key):
            logging.warning(f"Cannot update stale reference to {key=} (referenced from {srcRelKey=})")
            return

        skel.refresh()
        skel.write(update_relations=False)

    for srcRel in updateList:
        try:
            skel = skeletonByKind(srcRel["viur_src_kind"])()
        except AssertionError:
            logging.info(f"""Ignoring {srcRel.key!r} which refers to unknown kind {srcRel["viur_src_kind"]!r}""")
            continue
        if db.is_in_transaction():
            updateTxn(skel, srcRel["src"].key, srcRel.key)
        else:
            db.run_in_transaction(updateTxn, skel, srcRel["src"].key, srcRel.key)
    nextCursor = updateListQuery.getCursor()
    if len(updateList) == 5 and nextCursor:
        updateRelations(destKey, minChangeTime, changedBone, nextCursor)


@CallableTask
class TaskUpdateSearchIndex(CallableTaskBase):
    """
    This tasks loads and saves *every* entity of the given module.
    This ensures an updated searchIndex and verifies consistency of this data.
    """
    key = "rebuildSearchIndex"
    name = "Rebuild search index"
    descr = "This task can be called to update search indexes and relational information."

    def canCall(self) -> bool:
        """Checks wherever the current user can execute this task"""
        user = current.user.get()
        return user is not None and "root" in user["access"]

    def dataSkel(self):
        modules = ["*"] + listKnownSkeletons()
        modules.sort()
        skel = BaseSkeleton().clone()
        skel.module = SelectBone(descr="Module", values={x: translate(x) for x in modules}, required=True)
        return skel

    def execute(self, module, *args, **kwargs):
        usr = current.user.get()
        if not usr:
            logging.warning("Don't know who to inform after rebuilding finished")
            notify = None
        else:
            notify = usr["name"]

        if module == "*":
            for module in listKnownSkeletons():
                logging.info("Rebuilding search index for module %r", module)
                self._run(module, notify)
        else:
            self._run(module, notify)

    @staticmethod
    def _run(module: str, notify: str):
        Skel = skeletonByKind(module)
        if not Skel:
            logging.error("TaskUpdateSearchIndex: Invalid module")
            return
        RebuildSearchIndex.startIterOnQuery(Skel().all(), {"notify": notify, "module": module})


class RebuildSearchIndex(QueryIter):
    @classmethod
    def handleEntry(cls, skel: "SkeletonInstance", customData: dict[str, str]):
        skel.refresh()
        skel.write(update_relations=False)

    @classmethod
    def handleError(cls, skel, customData, exception) -> bool:
        logging.exception(f'{cls.__qualname__}.handleEntry failed on skel {skel["key"]=!r}: {exception}')
        try:
            logging.debug(f"{skel=!r}")
        except Exception:  # noqa
            logging.warning("Failed to dump skel")
            logging.debug(f"{skel.dbEntity=}")
        return True

    @classmethod
    def handleFinish(cls, totalCount: int, customData: dict[str, str]):
        QueryIter.handleFinish(totalCount, customData)
        if not customData["notify"]:
            return
        txt = (
            f"{conf.instance.project_id}: Rebuild search index finished for {customData['module']}\n\n"
            f"ViUR finished to rebuild the search index for module {customData['module']}.\n"
            f"{totalCount} records updated in total on this kind."
        )
        try:
            email.send_email(dests=customData["notify"], stringTemplate=txt, skel=None)
        except Exception as exc:  # noqa; OverQuota, whatever
            logging.exception(f'Failed to notify {customData["notify"]}')


# Vacuum Relations

@CallableTask
class TaskVacuumRelations(TaskUpdateSearchIndex):
    """
    Checks entries in viur-relations and verifies that the src-kind
    and it's RelationalBone still exists.
    """
    key = "vacuumRelations"
    name = "Vacuum viur-relations (dangerous)"
    descr = "Drop stale inbound relations for the given kind"

    def execute(self, module: str, *args, **kwargs):
        usr = current.user.get()
        if not usr:
            logging.warning("Don't know who to inform after rebuilding finished")
            notify = None
        else:
            notify = usr["name"]
        processVacuumRelationsChunk(module.strip(), None, notify=notify)


@CallDeferred
def processVacuumRelationsChunk(
    module: str, cursor, count_total: int = 0, count_removed: int = 0, notify=None
):
    """
    Processes 25 Entries and calls the next batch
    """
    query = db.Query("viur-relations")
    if module != "*":
        query.filter("viur_src_kind =", module)
    query.setCursor(cursor)
    for relation_object in query.run(25):
        count_total += 1
        if not (src_kind := relation_object.get("viur_src_kind")):
            logging.critical("We got an relation-object without a src_kind!")
            continue
        if not (src_prop := relation_object.get("viur_src_property")):
            logging.critical("We got an relation-object without a src_prop!")
            continue
        try:
            skel = skeletonByKind(src_kind)()
        except AssertionError:
            # The referenced skeleton does not exist in this data model -> drop that relation object
            logging.info(f"Deleting {relation_object.key} which refers to unknown kind {src_kind}")
            db.delete(relation_object)
            count_removed += 1
            continue
        if src_prop not in skel:
            logging.info(f"Deleting {relation_object.key} which refers to "
                         f"non-existing RelationalBone {src_prop} of {src_kind}")
            db.delete(relation_object)
            count_removed += 1
    logging.info(f"END processVacuumRelationsChunk {module}, "
                 f"{count_total} records processed, {count_removed} removed")
    if new_cursor := query.getCursor():
        # Start processing of the next chunk
        processVacuumRelationsChunk(module, new_cursor, count_total, count_removed, notify)
    elif notify:
        txt = (
            f"{conf.instance.project_id}: Vacuum relations finished for {module}\n\n"
            f"ViUR finished to vacuum viur-relations for module {module}.\n"
            f"{count_total} records processed, "
            f"{count_removed} entries removed"
        )
        try:
            email.send_email(dests=notify, stringTemplate=txt, skel=None)
        except Exception as exc:  # noqa; OverQuota, whatever
            logging.exception(f"Failed to notify {notify}")
