# -*- coding: utf-8 -*-
from server.bones import baseBone
from server import db
from google.appengine.api import search
import json
from server.tasks import PeriodicTask
from time import time
from datetime import datetime
import logging

class relationalBone( baseBone ):
	"""
		This is our magic class implementing relations.
		This implementation is read-efficient, e.g. filtering by relational-properties only costs an additional small-op for each entity returned.
		However, it costs several more write-ops for writing an entity to the db.
		(These costs are somewhat around additional (4+len(refKeys)+len(parentKeys)) write-ops for each referenced property))
		So dont use this if you expect data being read less frequently than written! (Sorry, we dont have a write-efficient method yet)
		To speedup writes to (maybe) referenced entities, information in these relations isnt updated instantly.
		There is a background task which runs periodically (default: every 4 hours) which updates the references to recently changed entities.
		As a result, you might see stale data for up to these four hours.
		Example:
		Entity A references Entity B.
		Both have a property "name".
		Entity B gets updated (it name changes).
		As "A" has a copy of entity "B"s values, you'll see "B"s old name inside the values of the relationalBone when fetching entity A.
		If you filter a list by relational properties, this will also use the old data! (Eg. filtering A's list by B's new name wont return any result)
		Currently, this is corrected by the background task, however its possible to consider other methods (eg. by probability).
	"""
	
	
	type = None
	refKeys = ["name"]
	parentKeys = []

	def __init__( self, type=None, refKeys=None, parentKeys=None, multiple=False, format="$(name)",  *args,**kwargs):
		"""
			Initialize a new relationalBone.
			@param type: Type of the referenced property. The this type must also match the modulname!
			@type type: String
			@param refKeys: A list of properties to include from the referenced property. These properties will be avaiable in the template without having to fetch the referenced property. Filtering is also only possible by properties named here!
			@type refKeys: List of Strings
			@param parentKeys: A list of properties from the current skeleton to include. If mixing filtering by relational properties and properties of the class itself, these must be named here.
			@type parentKeys: List of Strings
			@param multiple: If True, allow referencing multiple Elements of the given class. (Eg. n:n-relation. otherwise its n:1 )
			@type multiple: False
			@param format: Hint for the admin how to display such an relation. See admin/utils.py:formatString for more information
			@type format: String
		"""
		baseBone.__init__( self, *args, **kwargs )
		self.multiple = multiple
		self.format = format
		if type:
			self.type = type
		if self.type is None:
			raise NotImplementedError("Type of relationalbone's must not be None")
		if refKeys:
			self.refKeys=refKeys
		if parentKeys:
			self.parentKeys=parentKeys

	def unserialize( self, name, expando ):
		if name in expando.keys():
			val = expando[ name ]
			if self.multiple:
				self.value = []
				if not val:
					return( True )
				if isinstance(val, list):
					for res in val:
						try:
							self.value.append( json.loads( res ) )
						except:
							pass
				else:
					try:
						value = json.loads( val )
						if isinstance( value, dict ):
							self.value.append( value )
					except:
						pass
			else:
				if isinstance( val, list ) and len( val )>0:
					self.value = json.loads( val[0] )
				else:
					if val:
						self.value = json.loads( val )
					else:
						self.value = None

		else:
			self.value = None
		return( True )
	
	def serialize(self, key, entity ):
		if not self.value:
			entity.set( key, None, False )
		else:
			if self.multiple:
				res = []
				for val in self.value:
					res.append( json.dumps( val ) )
				entity.set( key, res, False )
			else:
				entity.set( key, json.dumps( self.value ), False )
		return( entity )
	
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
				val = getattr( skel, parentKey ).value
				if not ( isinstance( val, float ) or isinstance( val, int ) or isinstance( val, datetime ) or
					(isinstance( val, list ) and all( [ (isinstance( x, basestring ) or isinstance( x, float ) or isinstance( x, int ) or isinstance( x, datetime )) for x in val] ) ) ):
						#The value is neither a simple type (float,int,datetime) nor a list of these types) - force it to string
						val = unicode( val )
				parentValues[ parentKey ] = val
		dbVals = db.Query( skel.kindName+"_"+self.type+"_"+key ).ancestor( db.Key( id ) )
		for dbObj in dbVals.run():
			if not dbObj[ key+"_id" ] in [ x[key+"_id"] for x in values ]: #Relation has been removed
				db.Delete( dbObj.key() )
			else: # Relation: Updated
				data = [ x for x in values if x[key+"_id"]== dbObj[ key+"_id" ] ][0]
				for k,v in data.items():
					dbObj[ k ] = v
				for k,v in parentValues.items():
					dbObj[ k ] = v
				dbObj[ "viur_delayed_update_tag" ] = time()
				db.Put( dbObj )
				values.remove( data )
		# Add any new Relation
		for val in values:
			dbObj = db.Entity( skel.kindName+"_"+self.type+"_"+key, parent=db.Key( id ) )
			for k, v in val.items():
				dbObj[ k ] = v
			for k,v in parentValues.items():
				dbObj[ k ] = v
			dbObj[ "viur_delayed_update_tag" ] = time()
			db.Put( dbObj )
		
	def postDeletedHandler( self, skel, key, id ):
		db.Delete( [x for x in db.Query( skel.kindName+"_"+self.type+"_"+key ).ancestor( db.Key( id ) ).run( keysOnly=True ) ] )
	
	def rebuildData(self, *args, **kwargs ):
		pass
	
	def canUse( self, id ):
		return( True )
	

	def fromClient( self, value ):
		self.value = []
		res = []
		if not value:
			return( "Invalid value entered" )
		if self.multiple:
			if not isinstance( value, list ):
				if value:
					if value.find("\n")!=-1:
						for val in value.replace("\r\n","\n").split("\n"):
							valstr = val
							if valstr and self.canUse(  valstr  ):
								res.append(  valstr )
					else:
						valstr =  value
						if valstr and self.canUse(  valstr ):
							res.append( valstr )
			else:
				for val in value:
					valstr =  val 
					if valstr and self.canUse( valstr  ):
						res.append( valstr )
		else:
			valstr = value 
			if valstr and self.canUse( valstr ):
				res.append( valstr )
		
		if len( res ) == 0:
			return( "No value entered" )
		for r in res:
			try:
				entry = db.Get( db.Key( r ) )
			except: #Invalid key or something like that
				if not self.multiple:
					return( "Invalid entry selected" )
				continue
			if not entry or not entry.key().kind()==self.type: #Entry does not exist or has wrong type (is from another modul)
				if entry:
					logging.error("I got an id, which kind doesn't match my type! (Got: %s, my type %s)" % ( entry.key().kind(), self.type ) )
				continue
			if not self.multiple:
				#tmp = { k:v for k, v  in list(data.items()) if k in self.refKeys }
				#tmp["id"] = str( data["_id"] )
				self.value = { k: entry[k] for k in entry.keys() if k in self.refKeys }
				self.value["id"] = r
				return( None )
			else:
				tmp = { k: entry[k] for k in entry.keys() if k in self.refKeys }
				tmp["id"] = r
				self.value.append( tmp )
		if not self.value:
			return( "No value entered" )
		return( None )
		
	def buildDBFilter( self, name, skel, dbFilter, rawFilter ): #Fixme: Hm.... could be more...
		myKeys = [ x for x in rawFilter.keys() if x.startswith( "%s." % name ) ]
		if len( myKeys ) > 0 and not self.indexed:
			logging.warning( "Invalid searchfilter! %s is not indexed!" % name )
			raise RuntimeError()
		if len( myKeys ) > 0: #We filter by some properties
			#Create a new Filter based on our SubType and copy the parameters
			origFilter = dbFilter.datastoreQuery
			dbFilter.datastoreQuery = type( dbFilter.datastoreQuery )( skel.kindName+"_"+self.type+"_"+name )
			if origFilter:
				dbFilter.filter( origFilter )
			for key in myKeys:
				value = rawFilter[ key ]
				tmpdata = key.split("$")
				tmpdata[0] = tmpdata[0].replace(".", "_")
				if len( tmpdata ) > 1:
					if isinstance( value, list ):
						continue
					if tmpdata[1]=="lt":
						dbFilter.filter( "%s <" % tmpdata[0], value )
					elif tmpdata[1]=="gt":
						dbFilter.filter( "%s >" % tmpdata[0], value )
					elif tmpdata[1]=="lk":
						dbFilter.filter( "%s =", tmpdata[0], value )
					else:
						dbFilter.filter( "%s =", tmpdata[0], value )
				else:
					if isinstance( value, list ):
						if value:
							dbFilter.filter( ndb.GenericProperty( tmpdata[0] ).IN( value ) )
					else:
						dbFilter.filter( "%s =" % tmpdata[0], value )
		elif name in rawFilter.keys() and rawFilter[ name ].lower()=="none":
			dbFilter = dbFilter.filter( "%s =" % name, None )
		return( dbFilter )

	def buildDBSort( self, name, skel, dbFilter, rawFilter ):
		if "orderby" in list(rawFilter.keys()) and rawFilter["orderby"].startswith( "%s." % name ):
			#Create a new Filter based on our SubType and copy the parameters
			origFilter = dbFilter.filters
			origOrders = dbFilter.orders
			dbFilter = generateExpandoClass( skel.kindName+"_"+self.type+"_"+name ).query() #FIXME: Keys only!
			if origFilter:
				dbFilter = dbFilter.filter( origFilter )
			if origOrders:
				dbFilter = dbFilter.order( origOrders )
			dbFilter = dbFilter.filter( origFilter )
		return( dbFilter )

	def getSearchDocumentFields(self, name):
		if not self.value:
			return( [] )
		if self.multiple:
			data = self.value
		else:
			data = [ self.value ]
		res = []
		for rel in data:
			for k, v in rel.items():
				res.append( search.TextField( name="%s%s" % (name, k), value=unicode( v ) ) )
		return( res )

def findRelations( currentObj, depth=0, rels={} ):
	from server.skeleton import Skeleton
	if depth>4:
		return( rels )
	try:
		if issubclass( currentObj, Skeleton ):
			if not currentObj.kindName:
				return( rels )
			for key in dir( currentObj ):
				if key.startswith("__"):
					continue
				bone = getattr( currentObj, key )
				if isinstance( bone, relationalBone ):
					if not bone.type in rels.keys():
						rels[ bone.type ] = []
					data = ( currentObj.kindName, key, currentObj )
					if not data in rels[ bone.type ]:
						rels[ bone.type ].append( data )
			return( rels )
	except TypeError: #currentObj might not be a class
		pass
	for key in dir( currentObj ):
		if key.startswith("__"):
			continue
		rels = findRelations( getattr( currentObj, key ), depth+1, rels )
	return( rels )

@PeriodicTask(60*24)
def updateRelations():
	from server import conf
	for modul, referers in findRelations( conf["viur.mainApp"] ).items():
		for entry in db.Query( modul ).filter( "viur_delayed_update_tag >", 0).iter():
			for refTable, refKey, skel in referers:
				oldRelations = db.Query( refTable+"_"+modul+"_"+refKey )\
					.filter( "%s_id =" % refKey, str( entry.key() ) )\
					.filter( "viur_delayed_update_tag <", entry["viur_delayed_update_tag"] ).iter()
				for oldRelation in oldRelations:
					tmp = skel()
					tmp.fromDB( str(oldRelation.key().parent()) )
					for key in dir( tmp ):
						if not key.startswith("__") and isinstance( getattr( tmp, key ), relationalBone ):
							bone = getattr( tmp, key )
							if bone.value:
								if isinstance( bone.value, list ):
									bone.fromClient( [ x["id"] for x in bone.value] )
								else:
									bone.fromClient( bone.value["id"] )
					tmp.toDB( str(oldRelation.key().parent()), clearUpdateTag=True )
			tmp = db.Get( entry.key() ) #Reset its modified tag
			tmp["viur_delayed_update_tag"] = 0
			db.Put( tmp )

