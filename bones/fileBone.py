# -*- coding: utf-8 -*-
from server.bones import treeItemBone
from server.utils import generateExpandoClass
from google.appengine.ext import ndb
from server.utils import generateExpandoClass, markFileForDeletion
from google.appengine.api.images import get_serving_url

class fileBone( treeItemBone ):
	type = "file"
	refKeys = ["name", "meta_mime", "dlkey", "servingurl", "size"]
	
	def __init__(self, format="$(name)",*args, **kwargs ):
		super( fileBone, self ).__init__( format=format, *args, **kwargs )


	def postSavedHandler( self, key, skel, id, dbfields ):
		generateExpandoClass( self.type ) #Fixme: NDB...
		expClass = generateExpandoClass( skel.entityName+"_"+self.type+"_"+key )
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
		dbVals = expClass.query( ancestor = ndb.Key( urlsafe=id ) )
		for dbObj in dbVals:
			if not getattr( dbObj, key+"_id" ) in [ x[key+"_id"] for x in values ]: #Relation has been removed
				lockObjs = generateExpandoClass( "file" ).query(ancestor = dbObj.key ).fetch( 1000 )
				for lockObj in lockObjs:
					markFileForDeletion( lockObj.dlkey )
					lockObj.key.delete()
				dbObj.key.delete()
			else: # Relation: Updated
				data = [ x for x in values if x[key+"_id"]==getattr( dbObj, key+"_id" ) ][0]
				for k,v in data.items():
					setattr( dbObj, k, v )
				for k,v in parentValues.items():
					setattr( dbObj, k, v )
				dbObj.put()
				values.remove( data )
		# Add any new Relation
		for val in values:
			fileID = val[ key+"_id" ]
			origFileObj = ndb.Key( urlsafe=fileID ).get()
			if not origFileObj:
				continue
			if not "servingurl" in origFileObj._properties.keys() \
			and "meta_mime" in origFileObj._properties.keys() \
			and str(origFileObj.meta_mime).startswith("image/"):
				origFileObj.servingurl = get_serving_url( origFileObj.dlkey )
				origFileObj.put()
			dbObj = expClass( parent=ndb.Key( urlsafe=id ) )
			for k, v in val.items():
				setattr( dbObj, k, v )
			for k,v in parentValues.items():
				setattr( dbObj, k, v )
			dbObj.put()
			#Duplicate the File Obj
			lockObj = generateExpandoClass( "file" )( parent=dbObj.key )
			for tmpKey in origFileObj._properties.keys():
				setattr( lockObj, tmpKey, getattr( origFileObj, tmpKey ) )
			lockObj.weak = False
			lockObj.parentdir = None
			lockObj.put()

	def postDeletedHandler( self, skel, key, id ):
		expClass = generateExpandoClass( skel.entityName+"_"+self.type+"_"+key )
		parentObjs = expClass.query( ancestor=ndb.Key( urlsafe=id )).iter()
		for parentObj in parentObjs:
			files = generateExpandoClass( "file" ).query( ancestor=parentObj.key ).iter()
			for f in files:
				markFileForDeletion( f.dlkey )
				f.key.delete()
			parentObj.key.delete()
