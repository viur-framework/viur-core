# -*- coding: utf-8 -*-

import json, gzip
from time import sleep
from datetime import datetime, date, time
from server import utils, conf
from server.skeleton import Skeleton
from server.tasks import CallableTask, CallableTaskBase
from server.bones import *
from server.request import current as currentRequest
from google.appengine.api import files
from google.appengine.ext import ndb
from google.appengine.ext import blobstore
from google.appengine.api.images import get_serving_url
import logging


class BackupFile(object):
	__fileFormatVersion__ = 1
	
	class BlobReader( object ):
		"""
			This class allows reading the current blob from our backup-file.
			It ensures that only the current file is read (it will never read the backupfile beyont
			the end of the current blob.
		"""
		def __init__(self, f ):
			self.f = f
			self.finished = False
		
		def read(self, size ):
			"""
				Read roughly size bytes.
				Due to implementation-details, this size might not be exact (could be more or less bytes)
				@param size: Amount of bytes to read.
				@type size: int
			"""
			if self.finished:
				return("")
			if len( self.f.buffer ) < (2*size):
				self.f.fillBuffer( (2*size)-len( self.f.buffer ) ) #Data is Hex-Encoded - we need to read twice the amount
			if "\n" in self.f.buffer:
				res = self.f.buffer[ :self.f.buffer.find("\n") ]
				self.f.buffer = self.f.buffer[ self.f.buffer.find("\n")+1: ]
				self.finished = True
			else:
				res = self.f.buffer
				self.f.buffer = b""
			if len( res ) % 2 == 1 and len( res )> 1: #We got an odd string length
				self.f.buffer = res[-1]+self.f.buffer #Put the last char back onto the buffer
				res = res[ : -1 ]
			return( res.decode("hex") )
		
		def skipAll(self):
			"""
				Moves the cursor in our Backupfile to the end of the current blob.
				All bytes which not have been read yet are discarded.
				Does nothing if we are allready at the end of the blob.
			"""
			while not self.finished:
				self.read( 1024 )
	
	def __init__( self, filename, mode ):
		super( BackupFile, self ).__init__()
		assert mode == "r" or mode == "w"
		if filename.startswith("/gs/"):
			if mode == "w":
				self.gsFile = files.gs.create(filename, mime_type='application/octet-stream', acl='project-private')
				self.gsFileObj = files.open( self.gsFile, 'a' )
				self.f = gzip.GzipFile( mode=mode, fileobj=self.gsFileObj )
			else:
				self.f = gzip.GzipFile( mode=mode, fileobj=files.open( filename ) )
		elif filename.startswith("/bs/"):
			if mode == "w":
				self.gsFile = files.blobstore.create(mime_type='application/octet-stream')
				self.gsFileObj = files.open( self.gsFile, 'a' )
				self.f = gzip.GzipFile( mode=mode, fileobj=self.gsFileObj )
			else:
				self.f = gzip.GzipFile( mode=mode, fileobj=blobstore.BlobReader( filename[ 4: ] ) )
		else:
			raise( NotImplementedError() )
		self.mode = mode
		self.filename = filename
		self.buffer = b""
		versionString = "!M ViUR-Backup %s\n" % self.__fileFormatVersion__
		if mode == "r":
			self.fillBuffer(1024)
			assert self.buffer.startswith( versionString )
			self.buffer = self.buffer[ len( versionString ): ]
		else:
			self.f.write( versionString )
	
	def writeEntry(self, obj ):
		r = {}
		for k in obj._properties.keys():
			val = getattr( obj, k )
			if isinstance( val, datetime ):
				val = {"datetime" : val.strftime("%d.%m.%Y %H:%M:%S") }
			elif isinstance( val, time ):
				val = {"time" : val.strftime("%H:%M:%S") }
			elif isinstance( val, date ):
				val = {"date" : val.strftime("%d.%m.%Y") }
			elif isinstance( val, dict ): #Should not happen, but..
				val = {"dict": val }
			r[ k ] = val
			r["__id__"] = obj.key.urlsafe()
			r["__kind__"] = obj._get_kind()
		self.f.write( "!e %s\n" % json.dumps( r ).encode("hex") )
	
	def writeBlob( self, blobKey ):
		blobReader = blobstore.BlobReader( blobKey )
		blobInfo = blobstore.BlobInfo.get( blobKey )
		self.f.write( "!f %s %s " % (blobKey, blobInfo.content_type ) )
		data = blobReader.read(1024)
		while data:
			self.f.write( data.encode("hex") )
			data = blobReader.read(1024)
		self.f.write( "\n" )
	
	def fillBuffer( self, size ):
		tmp = self.f.read( size )
		assert len(tmp)>0
		self.buffer += tmp
	
	def iterEntries(self):
		"""
			Iterate over all dbentries in the file.
			Note: Assumed invariant is, that all entries form a contiguous block.
			(i.e. there is no blob between two entries)
		"""
		while 1:
			if not self.buffer:
				try:
					self.fillBuffer( 1024 )
				except AssertionError: #Were at the end of our file
					raise( StopIteration() )
			if not self.buffer.startswith( "!e" ):
				raise( StopIteration() )
			while not "\n" in self.buffer:
				self.fillBuffer( 1024 )
			resDict = json.loads( self.buffer[ 3:self.buffer.find("\n") ].decode("hex") )
			self.buffer = self.buffer[ self.buffer.find("\n")+1: ]
			id = resDict["__id__"]
			kind = resDict["__kind__"]
			del resDict["__id__"]
			del resDict["__kind__"]
			for k, v in resDict.items():
				if isinstance(v, dict):
					if "datetime" in v.keys():
						v = datetime.strptime(v["datetime"], "%d.%m.%Y %H:%M:%S")
					elif "time"  in v.keys():
						v = time.strptime(v["time"], "%d.%m.%Y %H:%M:%S")
					elif "date"  in v.keys():
						v = date.strptime(v["date"], "%d.%m.%Y")
					elif "dict"  in v.keys():
						v = v["dict"]
				resDict[k] = v
			obj = utils.generateExpandoClass( str(kind) )()
			for k, v in resDict.items():
				setattr( obj, k, v )
			newKey = ndb.Key(urlsafe=id)
			obj._key = newKey
			obj.key = newKey
			yield obj
	
	def iterBlobs(self):
		while 1:
			if not self.buffer:
				try:
					self.fillBuffer( 1024 )
				except AssertionError: #Were at the end of our file
					raise( StopIteration() )
			if not self.buffer.startswith( "!f " ):
				raise( StopIteration() )
			self.buffer = self.buffer[ 3: ]
			if not " " in self.buffer:
				self.fillBuffer( 1024 )
			assert " " in self.buffer
			blobKey = self.buffer[ : self.buffer.find(" ") ]
			self.buffer = self.buffer[ self.buffer.find(" ")+1: ]
			blobMime = self.buffer[ : self.buffer.find(" ") ]
			self.buffer = self.buffer[ self.buffer.find(" ")+1: ]
			blobReader = BackupFile.BlobReader( self )
			yield blobKey, blobMime, blobReader
			blobReader.skipAll()
	
	def close(self):
		if self.f:
			self.f.close()
			self.f = None
		if self.gsFileObj:
			self.gsFileObj.close()
			self.gsFileObj = None
		if self.gsFile:
			files.finalize( self.gsFile )
			if self.filename.startswith("/bs/"): #Were writing to blobstore
				newBlobKey = str(files.blobstore.get_blob_key( self.gsFile ))
				utils.markFileForDeletion( newBlobKey )
				repo, filename = self.filename[4:].split("/")
				assert repo
				lockObj = utils.generateExpandoClass( "file" )()
				lockObj.name = filename
				lockObj.name_idx = filename.lower()
				lockObj.meta_mime = "application/octet-stream"
				lockObj.dlkey = newBlobKey
				lockObj.parentdir=repo 
				lockObj.parentrepo=repo
				lockObj.size = 0
				lockObj.weak = False
				lockObj.put()
				logging.info("Backup DL-URL: /file/view/%s/%s" % (newBlobKey, filename.replace("/", "_") ) )
			self.gsFile = None

## Functions

def backup( fileName ):
	"""
		Creates a backup in the given file.
		Note: fileName must be in the form /gs/bucket_name/file_name
		or /bs/repository/filename
	"""
	modules = []
	kinds = []
	outFile =  BackupFile( fileName, "w" )
	logging.info("Backup started")
	# Backup db-entries
	for modulName in dir( conf["viur.mainApp"] ):
		if not modulName in modules:
			modules.append( modulName )
			modul = getattr( conf["viur.mainApp"], modulName )
			for key in dir( modul ):
				skel = getattr( modul, key )
				try:
					assert issubclass( skel, Skeleton )
					entityName = skel().entityName
					assert entityName
				except:
					continue
				if "%s %s" % ( modulName, entityName ) in kinds:
					continue
				kinds.append("%s %s" % ( modulName, entityName ))
				for entry in utils.generateExpandoClass( entityName ).query().iter():
					outFile.writeEntry( entry )
	# Backup Blobs
	for blob in blobstore.BlobInfo.all():
		outFile.writeBlob( blob.key() )
	outFile.close()
	logging.info("Backup finished!")

def restore( fileName ):
	modules = []
	kinds = []
	inFile =  BackupFile( fileName, "r" )
	logging.error("Restore started")
	if fileName.startswith("/bs/"): #Ensure our blob stays valid until we are done with it.
		flushDB( skipBlobs=[ fileName[4:] ] )
	else:
		flushDB(  )
	maxIDs = {}
	for entry in inFile.iterEntries():
		entry.put()
		kind = entry._get_kind()
		if not str(kind) in maxIDs.keys():
			maxIDs[ str(kind) ] = 0
		if entry.key.integer_id() and entry.key.integer_id()> maxIDs[ str(kind) ]:
			maxIDs[ str(kind) ] = entry.key.integer_id()
	#Ensure that the used id-ranges are blocked
	for k, v in maxIDs.items(): 
		utils.generateExpandoClass( str(k) ).allocate_ids( max=v )
	# Restore BlobKeys
	blobMap = {}
	for blobKey, blobMime, reader in inFile.iterBlobs():
		file_name = files.blobstore.create(mime_type=blobMime)
		with files.open(file_name, 'a') as f:
			data = reader.read( 1024 )
			while data:
				f.write( data )
				data = reader.read( 1024 )
		files.finalize(file_name)
		newBlobKey = files.blobstore.get_blob_key(file_name)
		blobMap[ blobKey ] = str(newBlobKey)
	#Fix file-base objects
	for entry in utils.generateExpandoClass( "file" ).query().iter():
		if entry.dlkey in blobMap.keys():
			entry.dlkey = blobMap[ entry.dlkey ]
			entry.servingurl = get_serving_url( entry.dlkey )
			entry.put()
	del inFile
	if fileName.startswith("/bs/"): #Drop the blob as we dont need it any more
		blobstore.delete( fileName[4:] )
	logging.info("Restore finished!")

def flushDB( skipBlobs=None, skipEntries=None ):
	if not currentRequest.get().isDevServer:
		utils.sendEMailToAdmins( "Warning: Database is about to be erased", "Someone requested to erase the database. "+\
								"To cancel this, log on to https://appengine.google.com/ and place this application "+\
								"into read-only mode and shutdown any backends. This is the 15 minutes warning!" )
		sleep( 60*10 )# Sleep 10 Minutes
		utils.sendEMailToAdmins( "Warning: Database is about to be erased", "Someone requested to erase the database. "+\
								"To cancel this, log on to https://appengine.google.com/ and place this application "+\
								"into read-only mode and shutdown any backends. Last warning!" )
		sleep( 60*5 )# Sleep antoher 5 Minutes
	for blob in blobstore.BlobInfo.all(): #Delete all blobs
		if skipBlobs and str(blob.key()) in skipBlobs:
			continue
		blob.delete()
	for dbKey in ndb.Query( default_options=ndb.QueryOptions( keys_only=True ) ).iter():
		if dbKey.kind().startswith("_") or ( skipEntries and str(dbKey.key.urlsafe()) in skipEntries ):
			continue
		dbKey.delete()

### Tasks ###

@CallableTask
class TaskBackup( CallableTaskBase ):
	"""This tasks loads and saves *every* entity of the given modul.
	This ensures an updated searchindex and verifies consistency of this data.
	"""
	id = "backupdatabase"
	name = u"Create a Backup"
	descr = u"Backups the Database, including uploaded files."
	direct = True
	
	def dataSkel(self):
		fileRepo = None
		fileRepo = getattr( conf["viur.mainApp"], "file" ).getAvailableRootNodes("")[0]["key"]
		skel = Skeleton( self.entityName )
		skel.dest = selectOneBone( descr="Backup target", required=True, values={"gs":"Google Storage", "file": "File" } )
		skel.filename = stringBone( descr="Filename", required=True )
		skel.filerepo = baseBone( descr="Dest File Repo", readOnly=True, defaultValue=fileRepo, visible=False )
		return( skel )

	def execute( self, dest=None, filename=None, filerepo=None,  *args, **kwargs ):
		if dest=="file" and filename and filerepo:
			backup( "/bs/%s/%s" % (filerepo, filename.replace("/", "_") ) )
		elif dest=="gs":
			backup("/gs/backups_mausbrand_de/%s" % filename.replace("/", "_") )
	
	def canCall( self ):
		return( True )
		
@CallableTask
class TaskRestore( CallableTaskBase ):
	"""This tasks loads and saves *every* entity of the given modul.
	This ensures an updated searchindex and verifies consistency of this data.
	"""
	id = "restoredatabase"
	name = u"Restore a Backup"
	descr = u"Restores the Database, including uploaded files."
	direct = True #FIXME: asd
	
	def dataSkel(self):
		fileRepo = None
		fileRepo = getattr( conf["viur.mainApp"], "file" ).getAvailableRootNodes("")[0]["key"]
		skel = Skeleton( self.entityName )
		skel.dest = selectOneBone( descr="Backup source", required=True, values={"gs":"Google Storage", "file": "File" } )
		skel.filename = stringBone( descr="GS Filename", required=False )
		skel.filerel = fileBone( descr="File", required=False )
		return( skel )

	def execute( self, dest=None, filename=None, filerel=None,  *args, **kwargs ):
		if dest=="file" and filerel:
			restore( "/bs/%s" %  filerel["dlkey"] )
		elif dest=="gs":
			restore( "/gs/backups_mausbrand_de/%s" %  filename )
	
	def canCall( self ):
		return( True )
		
