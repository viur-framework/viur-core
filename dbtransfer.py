#!/usr/bin/python2
# -*- coding: utf-8 -*-
from server.config import conf
import logging
import pickle
from server.skeleton import skeletonByKind, listKnownSkeletons
from datetime import datetime
from server.render.json.default import DefaultRender
from server import db
from server import request
from server import errors
from google.appengine.api import datastore, datastore_types
from google.appengine.datastore import datastore_query
from google.appengine.ext.blobstore import BlobInfo
import json
from server import exposed
from google.appengine.ext import blobstore
from google.appengine.api.images import get_serving_url
import collections
import cgi
from itertools import izip
from tasks import CallableTask, CallableTaskBase, callDeferred
from server.bones import *
from server.skeleton import Skeleton
from server import utils
import urllib
from google.appengine.api import urlfetch
from hashlib import sha256


class DbTransfer( object ):
	def __init__(self, *args, **kwargs ):
		return( super( DbTransfer, self ).__init__())

	def _checkKey(self, key, export=True):
		"""
			Utility function to compare the given key with the keys stored in our conf in constant time
			@param key: The key we should validate
			@type key: string
			@param export: If True, we validate against the export-key, otherwise the import-key
			@type export: bool
			@returns: True if the key is correct, False otherwise
		"""
		isValid = True
		if not isinstance( key, basestring ):
			isValid = False
		if export:
			expectedKey = conf["viur.exportPassword"]
		else:
			expectedKey = conf["viur.importPassword"]
		if not expectedKey:
			isValid = False
		if len(key)!=len(expectedKey):
			isValid = False
		for a,b in izip(str(key),str(expectedKey)):
			if a!=b:
				isValid = False
		return( isValid )

	@exposed
	def listModules(self, key):
		if not self._checkKey( key, export=False):
			raise errors.Forbidden()
		return( pickle.dumps( listKnownSkeletons() ) )

	@exposed
	def getCfg(self, modul, key ):
		if not self._checkKey( key, export=False):
			raise errors.Forbidden()
		skel = skeletonByKind( modul )
		assert skel is not None
		res = skel()
		r = DefaultRender()
		return( pickle.dumps( r.renderSkelStructure(res)))


	@exposed
	def getAppId(self, key, *args, **kwargs):
		if not self._checkKey( key, export=False):
			raise errors.Forbidden()
		return( pickle.dumps( db.Query("SharedConfData").get().key().app() ) ) #app_identity.get_application_id()

	def decodeFileName(self, name):
		# http://code.google.com/p/googleappengine/issues/detail?id=2749
		# Open since Sept. 2010, claimed to be fixed in Version 1.7.2 (September 18, 2012)
		# and still totally broken
		try:
			if name.startswith("=?"): #RFC 2047
				return( unicode( email.Header.make_header( email.Header.decode_header(name+"\n") ) ) )
			elif "=" in name and not name.endswith("="): #Quoted Printable
				return( decodestring( name.encode("ascii") ).decode("UTF-8") )
			else: #Maybe base64 encoded
				return( b64decode( name.encode("ascii") ).decode("UTF-8") )
		except: #Sorry - I cant guess whats happend here
			if isinstance( name, str ) and not isinstance( name, unicode ):
				try:
					return( name.decode("UTF-8", "ignore") )
				except:
					pass
			return( name )

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
		for key, value in request.current.get().request.params.items():
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
	def upload( self, oldkey, *args, **kwargs ):
		logging.error("got UPLOADS")
		res = []
		for upload in self.getUploads():
			fileName = self.decodeFileName( upload.filename )
			if str( upload.content_type ).startswith("image/"):
				try:
					servingURL = get_serving_url( upload.key() )
				except:
					servingURL = ""
			else:
				servingURL = ""
			res.append( {	"name": fileName,
					"size": upload.size,
					"mimetype": upload.content_type,
					"dlkey": str(upload.key()),
					"servingurl": servingURL,
					"parentdir": "",
					"parentrepo": "",
					"weak": False } )
			oldKeyHash = sha256(oldkey).hexdigest().encode("hex")
			e = db.Entity("viur-blobimportmap", name=oldKeyHash)
			e["newkey"] = str(upload.key())
			e["oldkey"] = oldkey
			e["servingurl"] = servingURL
			e["available"] = True
			db.Put(e)
		return( json.dumps( {"action":"addSuccess", "values":res } ) )

	@exposed
	def getUploadURL( self, key, *args, **kwargs ):
		if not self._checkKey( key, export=False):
			raise errors.Forbidden()
		return( blobstore.create_upload_url( "/dbtransfer/upload"  ) )

	@exposed
	def storeEntry(self, e, key ):
		if not self._checkKey( key, export=False):
			raise errors.Forbidden()
		entry = pickle.loads( e )
		for k in list(entry.keys())[:]:
			if isinstance(entry[k],str):
				entry[k] = entry[k].decode("UTF-8")
		key = db.Key( encoded=entry["id"] )
		logging.error( key.kind() )
		logging.error( key.id() )
		logging.error( key.name() )
		dbEntry = db.Entity( kind=key.kind(), parent=key.parent(), id=key.id(), _app=key.app(), name=key.name() )
		for k in entry.keys():
			if k!="id":
				val = entry[k]
				#if isinstance(val, dict) or isinstance(val, list):
				#	val = pickle.dumps( val )
				dbEntry[k] = val
		db.Put( dbEntry )

	@exposed
	def hasblob(self, blobkey, key ):
		if not self._checkKey( key, export=False):
			raise errors.Forbidden()
		try:
			oldKeyHash = sha256(blobkey).hexdigest().encode("hex")
			res = db.Get( db.Key.from_path("viur-blobimportmap", oldKeyHash))
			if res:
				if "available" in res.keys():
					return json.dumps(res["available"])
				else:
					return json.dumps(True)
		except:
			pass
		return json.dumps(False)


	@exposed
	def storeEntry2(self, e, key ):
		if not self._checkKey( key, export=False):
			raise errors.Forbidden()
		entry = pickle.loads( e.decode("HEX") )
		for k in list(entry.keys())[:]:
			if isinstance(entry[k],str):
				entry[k] = entry[k].decode("UTF-8")
		key = db.Key( encoded=utils.normalizeKey(entry["id"]) )

		logging.error( key.kind() )
		logging.error( key.id() )
		logging.error( key.name() )
		dbEntry = db.Entity( kind=key.kind(), parent=key.parent(), id=key.id(), name=key.name() )
		for k in entry.keys():
			if k!="id":
				val = entry[k]
				dbEntry[k] = val
		db.Put( dbEntry )
		try:
			skel =  skeletonByKind( key.kind() )()
		except:
			logging.error("Unknown Skeleton - skipping")
		skel.fromDB( str(dbEntry.key()) )
		skel.refresh()
		skel.toDB(clearUpdateTag=True)

	@staticmethod
	def genDict(obj):
		res = {}
		for k,v in obj.items():
			if not any( [isinstance(v,x) for x in [str, unicode, long, float, datetime, list, dict, bool, type(None)]] ):
				logging.error("UNKNOWN TYPE %s" % str(type(v)))
				v = unicode( v )
				logging.error( v )
			if isinstance( v, datastore_types.Text):
				v = unicode( v )
			elif isinstance(v ,datastore_types.Blob):
				continue
			elif isinstance(v ,datastore_types.BlobKey):
				continue
			elif isinstance(v ,datastore_types.ByteString):
				v = str( v )
			elif isinstance(v ,datastore_types.Category):
				v = unicode( v )
			elif isinstance(v ,datastore_types.Email):
				v = unicode( v )
			elif isinstance(v ,datastore_types.EmbeddedEntity):
				continue
			elif isinstance(v ,datastore_types.GeoPt):
				continue
			elif isinstance(v ,datastore_types.IM):
				continue
			elif isinstance(v ,datastore_types.Link):
				v = unicode( v )
			elif isinstance(v ,datastore_types.PhoneNumber):
				v = unicode( v )
			elif isinstance(v ,datastore_types.PostalAddress):
				v = unicode( v )
			elif isinstance(v ,datastore_types.Rating):
				v = long( v )
			if "datastore" in str(type(v)):
				logging.error(str(type(v)))
			res[ k ] = v
		res["id"] = str( obj.key() )
		return( res )

	@exposed
	def exportDb(self, cursor=None, key=None, *args, **kwargs):
		if not self._checkKey( key, export=True):
			raise errors.Forbidden()
		if cursor:
			c = datastore_query.Cursor(urlsafe=cursor)
		else:
			c = None
		q = datastore.Query( None, cursor=c )
		r = []
		for res in q.Run(limit=5):
			r.append( self.genDict( res ) )
		return( pickle.dumps( {"cursor": str(q.GetCursor().urlsafe()),"values":r}).encode("HEX"))

	@exposed
	def exportBlob(self, cursor=None, key=None,):
		if not self._checkKey( key, export=True):
			raise errors.Forbidden()
		q = BlobInfo.all()
		if cursor is not None:
			q.with_cursor( cursor )
		r = []
		for res in q.run(limit=5):
			r.append( str(res.key()) )
		return( pickle.dumps( {"cursor": str(q.cursor()),"values":r}).encode("HEX"))


	@exposed
	def iterValues(self, module, cursor=None, key=None):
		if not self._checkKey( key, export=True):
			raise errors.Forbidden()

		q = db.Query(module)

		if cursor:
			q.cursor(cursor)

		r = []
		for res in q.run(limit=99):
			r.append( self.genDict( res ) )

		return pickle.dumps({"cursor": str(q.getCursor().urlsafe()), "values": r} )

	@exposed
	def getEntry(self, module, id, key=None):
		if not self._checkKey( key, export=True):
			raise errors.Forbidden()

		res = db.Get(id)

		return pickle.dumps(self.genDict(res))


###### NEW ######


@CallableTask
class TaskTransferKind( CallableTaskBase ):
	"""This tasks loads and saves *every* entity of the given modul.
	This ensures an updated searchIndex and verifies consistency of this data.
	"""
	id = "transferkind"
	name = u"Transfer Data"
	descr = u"Copies the selected data to the given target application"
	direct = True

	def canCall( self ):
		"""Checks wherever the current user can execute this task
		@returns bool
		"""
		user = utils.getCurrentUser()
		return( user is not None and "root" in user["access"] )

	def dataSkel(self):
		modules = listKnownSkeletons()
		modules.append("*")
		#for modulName in dir( conf["viur.mainApp"] ):
		#	modul = getattr( conf["viur.mainApp"], modulName )
		#	if "editSkel" in dir( modul ) and not modulName in modules:
		#		modules.append( modulName )
		skel = Skeleton( self.kindName )
		skel["modul"] = selectOneBone( descr="Modul", values={ x: x for x in modules}, required=True )
		skel["target"] = stringBone( descr="URL to Target-Application", required=True, defaultValue="https://your-app-id.appspot.com/storeE" )
		skel["importkey"] = stringBone( descr="Import-Key", required=True)
		return( skel )

	def execute( self, modul=None, target=None, importkey=None, *args, **kwargs ):
		assert importkey
		if modul=="*":
			for module in listKnownSkeletons():
				iterExport( module, target, importkey, None )
		else:
			iterExport( modul, target, importkey, None )

@callDeferred
def iterExport( modul, target, importKey, cursor=None ):
	"""
		Processes 100 Entries and calls the next batch
	"""
	urlfetch.set_default_fetch_deadline(20)
	Skel = skeletonByKind( modul )
	if not Skel:
		logging.error("TaskUpdateSeachIndex: Invalid modul")
		return
	query = Skel().all().cursor( cursor )
	gotAtLeastOne = False
	startCursor = cursor
	query.run(100, keysOnly=True)
	endCursor = query.getCursor()
	logging.error("start")
	logging.error(startCursor)
	logging.error(endCursor.urlsafe())
	exportItems(modul, target, importKey, startCursor, endCursor.urlsafe())
	if startCursor is None or startCursor!=endCursor.urlsafe():
		iterExport(modul, target, importKey, endCursor.urlsafe())
	else:
		logging.error("FIN")
	return

@callDeferred
def exportItems( modul, target, importKey, startCursor, endCursor):
	Skel = skeletonByKind( modul )
	query = Skel().all().cursor( startCursor, endCursor )
	logging.error("exportItems")
	for item in query.run(250, keysOnly=False):
		flatItem = DbTransfer.genDict( item )
		formFields = {
			"e": pickle.dumps(flatItem).encode("HEX"),
			"key": importKey
		}
		result = urlfetch.fetch(        url=target,
		                                payload=urllib.urlencode(formFields),
		                                method=urlfetch.POST,
		                                headers={'Content-Type': 'application/x-www-form-urlencoded'})
		logging.error(result)