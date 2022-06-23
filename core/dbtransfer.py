#!/usr/bin/python2
import cgi
import collections
import json
import logging
import pickle
import urllib
from datetime import datetime
from hashlib import sha256
from viur.core.prototypes.hierarchy import HierarchySkel

from viur.core import conf, db, email, errors, exposed, utils
from viur.core.bones import *
from viur.core.modules.file import decodeFileName
from viur.core.prototypes.tree import TreeLeafSkel
from viur.core.render.json.default import DefaultRender
from viur.core.skeleton import BaseSkeleton, listKnownSkeletons, skeletonByKind
from viur.core.tasks import CallableTask, CallableTaskBase, callDeferred
from viur.core.utils import currentRequest


class DbTransfer(object):

    def _checkKey(self, key: str, export: bool = True):
        """
            Utility function to compare the given key with the keys stored in our conf in constant time
            :param key: The key we should validate
            :param export: If True, we validate against the export-key, otherwise the import-key
            :returns: True if the key is correct, False otherwise
        """
        isValid = True
        if not isinstance(key, str):
            isValid = False
        if export:
            expectedKey = conf["viur.exportPassword"]
        else:
            expectedKey = conf["viur.importPassword"]
        if not expectedKey:
            isValid = False
        if len(key) != len(expectedKey):
            isValid = False
        for a, b in zip(str(key), str(expectedKey)):
            if a != b:
                isValid = False
        return isValid

    @exposed
    def listModules(self, key):
        if not self._checkKey(key, export=False):
            raise errors.Forbidden()
        return pickle.dumps(listKnownSkeletons())

    @exposed
    def getCfg(self, module, key):
        if not self._checkKey(key, export=False):
            raise errors.Forbidden()
        skel = skeletonByKind(module)
        assert skel is not None
        res = skel()
        r = DefaultRender()
        return pickle.dumps(r.renderSkelStructure(res))

    @exposed
    def getAppId(self, key, *args, **kwargs):
        if not self._checkKey(key, export=False):
            raise errors.Forbidden()
        return pickle.dumps("hsk-py3-test")
        # FIXME!
        return pickle.dumps(db.Query("SharedConfData").getEntry().key().app()))  # app_identity.get_application_id(

    def getUploads(self, field_name=None):
        """
            Get uploads sent to this handler.
            Cheeky borrowed from blobstore_handlers.py - © 2007 Google Inc.

            Args:
                field_name: Only select uploads that were sent as a specific field.

            Returns:
                A list of BlobInfo records corresponding to each upload.
                Empty list if there are no blob-info records for field_name.

        """
        uploads = collections.defaultdict(list)
        for key, value in currentRequest.get().request.params.items():
            if isinstance(value, cgi.FieldStorage):
                if 'blob-key' in value.type_options:
                    uploads[key].append(blobstore.parse_blob_info(value))
        if field_name:
            return list(uploads.get(field_name, []))
        else:
            results = []
            for uploads in uploads.itervalues():
                results.extend(uploads)
            return results

    @exposed
    def upload(self, oldkey, *args, **kwargs):
        res = []
        for upload in self.getUploads():
            fileName = decodeFileName(upload.filename)
            if str(upload.content_type).startswith("image/"):
                try:
                    servingURL = get_serving_url(upload.key())
                except:
                    servingURL = ""
            else:
                servingURL = ""
            res.append({"name": fileName,
                        "size": upload.size,
                        "mimetype": upload.content_type,
                        "dlkey": str(upload.key()),
                        "servingurl": servingURL,
                        "parentdir": "",
                        "parentrepo": "",
                        "weak": False})

            oldkey = decodeFileName(oldkey)
            oldKeyHash = sha256(oldkey).hexdigest().encode("hex")

            e = db.Entity("viur-blobimportmap", name=oldKeyHash)
            e["newkey"] = str(upload.key())
            e["oldkey"] = oldkey
            e["servingurl"] = servingURL
            e["available"] = True
            db.Put(e)

        return json.dumps({"action": "addSuccess", "values": res})

    @exposed
    def getUploadURL(self, key, *args, **kwargs):
        if not self._checkKey(key, export=False):
            raise errors.Forbidden()
        return blobstore.create_upload_url("/dbtransfer/upload")

    @exposed
    def storeEntry(self, e, key):
        if not self._checkKey(key, export=False):
            raise errors.Forbidden()
        entry = pickle.loads(bytes.fromhex(e))

        for k in list(entry.keys()):
            if isinstance(entry[k], bytes):
                entry[k] = entry[k].decode("UTF-8")

        for k in list(entry.keys()):
            if k in entry and "." in k:
                base = k.split(".")[0]
                tmpDict = {}
                for subkey in list(entry.keys()):
                    if subkey.startswith("%s." % base):
                        postfix = subkey.split(".")[1]
                        tmpDict[postfix] = entry[subkey]
                        del entry[subkey]
                entry[base] = tmpDict
        for k in list(entry.keys()):
            if "-" in k:
                entry[k.replace("-", "_")] = entry[k]
                del entry[k]
        if "key" in entry:
            key = db.Key(*entry["key"].split("/"))
        else:
            raise AttributeError()

        dbEntry = db.Entity(key)  # maybe some more fixes here ?
        for k in entry.keys():
            if k != "key":
                val = entry[k]
                # if isinstance(val, dict) or isinstance(val, list):
                #    val = pickle.dumps( val )
                dbEntry[k] = val
        # dbEntry = fixUnindexed(dbEntry)
        try:
            db.Put(dbEntry)
        except:
            from pprint import pprint
            pprint(dbEntry)
            raise

    @exposed
    def hasblob(self, blobkey, key):
        if not self._checkKey(key, export=False):
            raise errors.Forbidden()
        try:
            oldKeyHash = sha256(blobkey).hexdigest().encode("hex")
            res = db.Get(db.Key.from_path("viur-blobimportmap", oldKeyHash))
            if res:
                if "available" in res:
                    return json.dumps(res["available"])
                else:
                    return json.dumps(True)
        except:
            pass
        return json.dumps(False)

    @exposed
    def storeEntry2(self, e, key):
        if not self._checkKey(key, export=False):
            raise errors.Forbidden()
        entry = pickle.loads(e.decode("HEX"))
        if not "key" in entry and "id" in entry:
            entry["key"] = entry["id"]
        for k in list(entry.keys())[:]:
            if isinstance(entry[k], str):
                entry[k] = entry[k].decode("UTF-8")
        key = db.Key(encoded=utils.normalizeKey(entry["key"]))

        dbEntry = db.Entity(kind=key.kind(), parent=key.parent(), id=key.id(),
                            name=key.name())  # maybe some more fixes here ?
        for k in entry.keys():
            if k != "key":
                val = entry[k]
                dbEntry[k] = val
        db.Put(dbEntry)
        if dbEntry.key().id():
            # Ensure the Datastore knows that it's id is in use
            datastore._GetConnection()._reserve_keys([dbEntry.key()])
        try:
            skel = skeletonByKind(key.kind())()
        except:
            logging.error("Unknown Skeleton - skipping")
        skel.fromDB(str(dbEntry.key()))
        skel.refresh()
        skel.toDB(clearUpdateTag=True)

    @staticmethod
    def genDict(obj):
        res = {}
        for k, v in obj.items():
            if not any([isinstance(v, x) for x in [str, unicode, long, float, datetime, list, dict, bool, type(None)]]):
                logging.error("UNKNOWN TYPE %s" % str(type(v)))
                v = str(v)
                logging.error(v)
            if isinstance(v, datastore_types.Text):
                v = str(v)
            elif isinstance(v, datastore_types.Blob):
                continue
            elif isinstance(v, datastore_types.BlobKey):
                continue
            elif isinstance(v, datastore_types.ByteString):
                v = str(v)
            elif isinstance(v, datastore_types.Category):
                v = str(v)
            elif isinstance(v, datastore_types.Email):
                v = str(v)
            elif isinstance(v, datastore_types.EmbeddedEntity):
                continue
            elif isinstance(v, datastore_types.GeoPt):
                continue
            elif isinstance(v, datastore_types.IM):
                continue
            elif isinstance(v, datastore_types.Link):
                v = str(v)
            elif isinstance(v, datastore_types.PhoneNumber):
                v = str(v)
            elif isinstance(v, datastore_types.PostalAddress):
                v = str(v)
            elif isinstance(v, datastore_types.Rating):
                v = long(v)
            if "datastore" in str(type(v)):
                logging.error(str(type(v)))
            res[k] = v
        res["key"] = str(obj.key())
        return res

    @exposed
    def exportDb(self, cursor=None, key=None, *args, **kwargs):
        if not self._checkKey(key, export=True):
            raise errors.Forbidden()
        if cursor:
            c = datastore_query.Cursor(urlsafe=cursor)
        else:
            c = None
        q = datastore.Query(None, cursor=c)
        r = []
        for res in q.Run(limit=5):
            r.append(self.genDict(res))
        return pickle.dumps({"cursor": str(q.GetCursor().urlsafe()), "values": r}).encode("HEX")

    @exposed
    def exportBlob(self, cursor=None, key=None):
        if not self._checkKey(key, export=True):
            raise errors.Forbidden()
        q = BlobInfo.all()
        if cursor is not None:
            q.with_cursor(cursor)
        r = []
        for res in q.run(limit=16):
            r.append(str(res.key()))
        return pickle.dumps({"cursor": str(q.cursor()), "values": r}).encode("HEX")

    @exposed
    def exportBlob2(self, cursor=None, key=None):
        if not self._checkKey(key, export=True):
            raise errors.Forbidden()

        q = BlobInfo.all()

        if cursor is not None:
            q.with_cursor(cursor)

        r = []
        for res in q.run(limit=16):
            r.append({"key": str(res.key()), "content_type": res.content_type})

        return pickle.dumps({"cursor": str(q.cursor()), "values": r}).encode("HEX")

    @exposed
    def iterValues(self, module, cursor=None, key=None):
        if not self._checkKey(key, export=True):
            raise errors.Forbidden()

        q = db.Query(module)

        if cursor:
            q.cursor(cursor)

        r = []
        for res in q.run(limit=99):
            r.append(self.genDict(res))

        return pickle.dumps({"cursor": str(q.getCursor().urlsafe()), "values": r})

    @exposed
    def iterValues2(self, module, cursor=None, key=None):
        if not self._checkKey(key, export=True):
            raise errors.Forbidden()

        q = db.Query(module)

        if cursor:
            q.cursor(cursor)

        r = []
        for res in q.run(limit=32):
            r.append(self.genDict(res))

        return pickle.dumps({"cursor": str(q.getCursor().urlsafe()), "values": r}).encode("HEX")

    @exposed
    def getEntry(self, module, id, key=None):
        if not self._checkKey(key, export=True):
            raise errors.Forbidden()

        res = db.Get(id)

        return pickle.dumps(self.genDict(res))


###### NEW ######

# --- export ---
@CallableTask
class TaskExportKind(CallableTaskBase):
    key = "exportkind"
    name = u"Export data kinds to other app"
    descr = u"Copies the selected data to the given target application"
    direct = True

    def canCall(self) -> bool:
        user = utils.getCurrentUser()
        return user is not None and "root" in user["access"]

    def dataSkel(self):
        skel = BaseSkeleton(cloned=True)
        skel.module = SelectBone(descr="Kinds", values=listKnownSkeletons(), multiple=True, required=True)
        skel.target = StringBone(descr="URL to Target-Application", required=True,
                                 defaultValue="https://your-app-id.appspot.com/dbtransfer/storeEntry2")
        skel.importkey = StringBone(descr="Import-Key", required=True)
        return skel

    def execute(self, module, target, importkey, *args, **kwargs):
        for mod in module:
            iterExport(mod, target, importkey)


@callDeferred
def iterExport(module, target, importKey, cursor=None):
    """
        Processes 100 Entries and calls the next batch
    """
    urlfetch.set_default_fetch_deadline(20)
    Skel = skeletonByKind(module)
    if not Skel:
        logging.error("TaskExportKind: Invalid module")
        return
    query = Skel().all().cursor(cursor)

    startCursor = cursor
    query.run(100)
    endCursor = query.getCursor().urlsafe()

    exportItems(module, target, importKey, startCursor, endCursor)

    if startCursor is None or startCursor != endCursor:
        iterExport(module, target, importKey, endCursor)


@callDeferred
def exportItems(module, target, importKey, startCursor, endCursor):
    Skel = skeletonByKind(module)
    query = Skel().all().cursor(startCursor, endCursor)

    for item in query.run(250):
        flatItem = DbTransfer.genDict(item)
        formFields = {
            "e": pickle.dumps(flatItem).encode("HEX"),
            "key": importKey
        }
        result = urlfetch.fetch(url=target,
                                payload=urllib.urlencode(formFields),
                                method=urlfetch.POST,
                                headers={'Content-Type': 'application/x-www-form-urlencoded'})

    if startCursor == endCursor:
        try:
            email.sendEMailToAdmins("Export of kind %s finished" % module,
                                    "ViUR finished to export kind %s to %s.\n" % (module, target))
        except:  # OverQuota, whatever
            pass


# --- import ---

@CallableTask
class TaskImportKind(CallableTaskBase):
    key = "importkind"
    name = u"Import data kinds from other app"
    descr = u"Copies the selected data from the given source application"
    direct = True

    def canCall(self) -> bool:
        user = utils.getCurrentUser()
        return user is not None and "root" in user["access"]

    def dataSkel(self):
        skel = BaseSkeleton(cloned=True)

        skel.module = SelectBone(descr="Kinds", values=listKnownSkeletons(), multiple=True, required=True)
        skel.source = StringBone(descr="URL to Source-Application", required=True,
                                 defaultValue="https://<your-app-id>.appspot.com/dbtransfer/iterValues2")
        skel.exportkey = StringBone(descr="Export-Key", required=True, defaultValue="")

        return skel

    def execute(self, module, source, exportkey, *args, **kwargs):
        for mod in module:
            iterImport(mod, source, exportkey)


@callDeferred
def iterImport(module, target, exportKey, cursor=None, amount=0):
    """
        Processes 100 Entries and calls the next batch
    """
    urlfetch.set_default_fetch_deadline(20)

    payload = {"module": module,
               "key": exportKey}
    if cursor:
        payload.update({"cursor": cursor})

    result = urlfetch.fetch(url=target,
                            payload=urllib.urlencode(payload),
                            method=urlfetch.POST,
                            headers={'Content-Type': 'application/x-www-form-urlencoded'})

    if result.status_code == 200:
        res = pickle.loads(result.content.decode("HEX"))
        skel = skeletonByKind(module)()
        logging.info("%s: %d new entries fetched, total %d entries fetched" % (module, len(res["values"]), amount))

        if len(res["values"]) == 0:
            try:
                email.sendEMailToAdmins("Import of kind %s finished with %d entities" % (module, amount),
                                        "ViUR finished to import %d entities of "
                                        "kind %s from %s.\n" % (amount, module, target))
            except:  # OverQuota, whatever
                logging.error("Unable to send Email")

            return

        for entry in res["values"]:
            for k in list(entry.keys())[:]:
                if isinstance(entry[k], str):
                    entry[k] = entry[k].decode("UTF-8")

            if not "key" in entry:
                entry["key"] = entry["id"]

            key = db.Key(encoded=utils.normalizeKey(entry["key"]))

            # Special case: Convert old module root nodes!!!
            if module.endswith("_rootNode") and key.name() and "_modul_" in key.name():
                name = key.name().replace("_modul_", "_module_")
            else:
                name = key.name()

            dbEntry = db.Entity(kind=key.kind(), parent=key.parent(), id=key.id(), name=name)

            for k in entry.keys():
                if k == "key":
                    continue

                dbEntry[k] = entry[k]

                # Special case: Convert old module root nodes!!!
                if (isinstance(skel, (HierarchySkel, TreeLeafSkel))
                    and k in ["parentdir", "parententry", "parentrepo"]
                    and entry[k]):

                    key = db.Key(encoded=str(entry[k]))
                    if key.parent():
                        parent = db.Key(encoded=utils.normalizeKey(key.parent()))
                    else:
                        parent = None

                    if key.id_or_name() and "_modul_" in str(key.id_or_name()):
                        name = key.id_or_name().replace("_modul_", "_module_")
                    else:
                        name = key.id_or_name()

                    dbEntry[k] = str(db.Key.from_path(key.kind(), name, parent=parent))

            db.Put(dbEntry)
            skel.fromDB(str(dbEntry.key()))
            skel.refresh()
            skel.toDB(clearUpdateTag=True)
            amount += 1

        iterImport(module, target, exportKey, res["cursor"], amount)
