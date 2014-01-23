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
from google.appengine.api import datastore, datastore_types
from google.appengine.datastore import datastore_query
from google.appengine.ext.blobstore import BlobInfo
import json
from server import exposed
from google.appengine.ext import blobstore
from google.appengine.api.images import get_serving_url
import collections
import cgi


class DbTransfer( object ):
	def __init__(self, *args, **kwargs ):
		return( super( DbTransfer, self ).__init__())

	def listModules(self):
		return( pickle.dumps( listKnownSkeletons() ) )
	listModules.exposed=True

	def getCfg(self, modul ):
		skel = skeletonByKind( modul )
		assert skel is not None
		res = skel()
		r = DefaultRender()
		return( pickle.dumps( r.renderSkelStructure(res)))
	getCfg.exposed=True

	def getAppId(self, *args, **kwargs):
		return( pickle.dumps( db.Query("SharedConfData").get().key().app() ) ) #app_identity.get_application_id()
	getAppId.exposed=True

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
	def upload( self,  *args, **kwargs ):
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
		return( json.dumps( {"action":"addSuccess", "values":res } ) )

	def getUploadURL( self, *args, **kwargs ):
		return( blobstore.create_upload_url( "/dbtransfer/upload"  ) )
	getUploadURL.exposed=True

	def storeEntry(self, e):
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
	storeEntry.exposed=True

	def genDict(self, obj):
		res = {}
		for k,v in obj.items():
			if not any( [isinstance(v,x) for x in [str, unicode, long, float, datetime.datetime, list, dict, bool, type(None)]] ):
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


	def exportDb(self, cursor=None, backupkey=None, *args, **kwargs):
		global backupKey
		assert backupKey==backupkey
		if cursor:
			c = datastore_query.Cursor(urlsafe=cursor)
		else:
			c = None
		q = datastore.Query( None, cursor=c )
		r = []
		for res in q.Run(limit=5):
			r.append( self.genDict( res ) )
		return( pickle.dumps( {"cursor": str(q.GetCursor().urlsafe()),"values":r}).encode("HEX"))
	exportDb.exposed=True

	def exportBlob(self, cursor=None, backupkey=None,):
		global backupKey
		assert backupKey==backupkey
		q = BlobInfo.all()
		if cursor is not None:
			q.with_cursor( cursor )
		r = []
		for res in q.run(limit=5):
			r.append( str(res.key()) )
		return( pickle.dumps( {"cursor": str(q.cursor()),"values":r}).encode("HEX"))
	exportBlob.exposed=True

