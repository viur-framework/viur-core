# -*- coding: utf-8 -*-
from server.bones import treeItemBone
from server import db
from server.utils import markFileForDeletion
from google.appengine.api.images import get_serving_url

class fileBone( treeItemBone ):
	type = "file"
	refKeys = ["name", "meta_mime", "dlkey", "servingurl", "size"]
	
	def __init__(self, format="$(name)",*args, **kwargs ):
		super( fileBone, self ).__init__( format=format, *args, **kwargs )

	def postSavedHandler( self, key, skel, id, dbfields ):
		if not self.value:
			values = []
		elif isinstance( self.value, dict ):
			values = [ dict( (key+"_"+k,v) for k,v in self.value.items() ) ]
		else:
			values = [ dict( (key+"_"+k,v) for k,v in x.items() ) for x in self.value ]
		parentValues = {}
		for parentKey in self.parentKeys:
			if parentKey in dir( skel ):
				parentValues[ parentKey ] = unicode( getattr( skel, parentKey ).value )
		dbVals = db.Query( skel.kindName+"_"+self.type+"_"+key ).ancestor( db.Key( id ) ).run()
		for dbObj in dbVals:
			if not dbObj[ key+"_id" ] in [ x[key+"_id"] for x in values ]: #Relation has been removed
				lockObjs = db.Query( "file", ancestor = dbObj.key() ).run( 100 )
				for lockObj in lockObjs:
					markFileForDeletion( lockObj["dlkey"] )
					db.Delete( lockObj.key() )
				db.Delete( dbObj.key() )
			else: # Relation: Updated
				data = [ x for x in values if x[key+"_id"]==dbObj[ key+"_id" ] ][0]
				for k,v in data.items():
					dbObj[ k ] = v
				for k,v in parentValues.items():
					dbObj[ k ] = v
				db.Put( dbObj )
				values.remove( data )
		# Add any new Relation
		for val in values:
			fileID = val[ key+"_id" ]
			try:
				origFileObj = db.Get( db.Key( fileID ) )
				assert origFileObj
			except:
				pass
			if not "servingurl" in origFileObj.keys() \
			and "meta_mime" in origFileObj.keys() \
			and str(origFileObj["meta_mime"]).startswith("image/"):
				origFileObj["servingurl"] = get_serving_url( origFileObj["dlkey"] )
				db.Put( origFileObj )
			dbObj = db.Entity(skel.kindName+"_"+self.type+"_"+key, parent=db.Key( id ) )
			for k, v in val.items():
				dbObj[ k ] = v
			for k,v in parentValues.items():
				dbObj[ k ] = v
			db.Put( dbObj )
			#Duplicate the File Obj
			lockObj = db.Entity( "file", parent=dbObj.key() )
			for tmpKey in origFileObj.keys():
				lockObj[ tmpKey ] = origFileObj[ tmpKey ]
			lockObj["weak"] = False
			lockObj["parentdir"] = None
			db.Put( lockObj )

	def postDeletedHandler( self, skel, key, id ):
		parentObjs = db.Query( skel.kindName+"_"+self.type+"_"+key ).ancestor( db.Key( id ) ).run()
		for parentObj in parentObjs:
			files = db.Query( "file", ancestor=parentObj.key() ).run()
			for f in files:
				markFileForDeletion( f["dlkey"] )
				db.Delete( f.key() )
			db.Delete( parentObj.key() )
