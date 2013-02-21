# -*- coding: utf-8 -*-
from server.bones import baseBone
from google.appengine.ext import ndb
from google.appengine.api import search
from server.utils import generateExpandoClass
import json
from server.tasks import PeriodicTask
from time import time
from datetime import datetime

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
			self.type=type
		if refKeys:
			self.refKeys=refKeys
		if parentKeys:
			self.parentKeys=parentKeys

	def unserialize( self, name, expando ):
		if name in expando._properties.keys():
			val = getattr( expando, name )
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
	
	def serialize(self, key ):
		if not self.value:
			return( {key:None } )
		if self.multiple:
			res = []
			for val in self.value:
				res.append( json.dumps( val ) )
			return( {key: res } )
		else:
			return( {key: json.dumps( self.value ) } )
		return( {key: None } )
	
	def postSavedHandler( self, key, skel, id, dbfields ):
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
				val = getattr( skel, parentKey ).value
				if not ( isinstance( val, float ) or isinstance( val, int ) or isinstance( val, datetime ) or
					(isinstance( val, list ) and all( [ (isinstance( x, basestring ) or isinstance( x, float ) or isinstance( x, int ) or isinstance( x, datetime )) for x in val] ) ) ):
						#The value is neither a simple type (float,int,datetime) nor a list of these types) - force it to string
						val = unicode( val )
				parentValues[ parentKey ] = val
		dbVals = expClass.query( ancestor = ndb.Key( urlsafe=id ) )
		for dbObj in dbVals.iter():
			if not getattr( dbObj, key+"_id" ) in [ x[key+"_id"] for x in values ]: #Relation has been removed
				dbObj.key.delete()
			else: # Relation: Updated
				data = [ x for x in values if x[key+"_id"]==getattr( dbObj, key+"_id" ) ][0]
				for k,v in data.items():
					setattr( dbObj, k, v )
				for k,v in parentValues.items():
					setattr( dbObj, k, v )
				setattr( dbObj, "viur_delayed_update_tag", time() )
				dbObj.put()
				values.remove( data )
		# Add any new Relation
		for val in values:
			dbObj = expClass( parent=ndb.Key( urlsafe=id ) )
			for k, v in val.items():
				setattr( dbObj, k, v )
			for k,v in parentValues.items():
				setattr( dbObj, k, v )
			setattr( dbObj, "viur_delayed_update_tag", time() )
			dbObj.put()
		
	def postDeletedHandler( self, skel, key, id ):
		expClass = generateExpandoClass( skel.entityName+"_"+self.type+"_"+key )
		ndb.delete_multi( [x for x in expClass.query( ancestor = ndb.Key( urlsafe=id )).iter(keys_only=True) ] ) #keys_only=True
	
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
		expClass = generateExpandoClass( self.type )
		for r in res:
			try:
				entry = ndb.Key( urlsafe=r ).get()
			except: #Invalid key or something like that
				if not self.multiple:
					return( "Invalid entry selected" )
				continue
			if not entry or not entry.key.kind()==self.type: #Entry does not exist or has wrong type (is from another modul)
				continue
			if not self.multiple:
				#tmp = { k:v for k, v  in list(data.items()) if k in self.refKeys }
				#tmp["id"] = str( data["_id"] )
				self.value = { k:getattr(entry,k) for k in entry._properties.keys() if k in self.refKeys }
				self.value["id"] = r
				return( None )
			else:
				tmp = { k:getattr(entry,k) for k in entry._properties.keys() if k in self.refKeys }
				tmp["id"] = r
				self.value.append( tmp )
		if not self.value:
			return( "No value entered" )
		return( None )
		
	def buildDBFilter( self, name, skel, dbFilter, rawFilter ): #Fixme: Hm.... could be more...
		myKeys = [ x for x in rawFilter.keys() if x.startswith( "%s." % name ) ]
		if len( myKeys ) > 0 and not self.searchable:
			logging.warning( "Invalid searchfilter! %s is not searchable!" % name )
			raise RuntimeError()
		if len( myKeys ) > 0: #We filter by some properties
			#Create a new Filter based on our SubType and copy the parameters
			origFilter = dbFilter.filters
			dbFilter = generateExpandoClass( skel.entityName+"_"+self.type+"_"+name ).query()
			if origFilter:
				dbFilter = dbFilter.filter( origFilter )
			for key in myKeys:
				value = rawFilter[ key ]
				tmpdata = key.split("$")
				tmpdata[0] = tmpdata[0].replace(".", "_")
				if len( tmpdata ) > 1:
					if isinstance( value, list ):
						continue
					if tmpdata[1]=="lt":
						dbFilter = dbFilter.filter( ndb.GenericProperty( tmpdata[0] ) < value )
					elif tmpdata[1]=="gt":
						dbFilter = dbFilter.filter( ndb.GenericProperty( tmpdata[0] ) > value )
					elif tmpdata[1]=="lk":
						dbFilter = dbFilter.filter( ndb.GenericProperty( tmpdata[0] ) == value )
					else:
						dbFilter = dbFilter.filter( ndb.GenericProperty( tmpdata[0] ) == value )
				else:
					if isinstance( value, list ):
						if value:
							dbFilter = dbFilter.filter( ndb.GenericProperty( tmpdata[0] ).IN( value ) )
					else:
						dbFilter = dbFilter.filter( ndb.GenericProperty( tmpdata[0] ) == value )
		elif name in rawFilter.keys() and rawFilter[ name ].lower()=="none":
			dbFilter = dbFilter.filter( ndb.GenericProperty( name ) == None )
		return( dbFilter )

	def buildDBSort( self, name, skel, dbFilter, rawFilter ):
		if "orderby" in list(rawFilter.keys()) and rawFilter["orderby"].startswith( "%s." % name ):
			#Create a new Filter based on our SubType and copy the parameters
			origFilter = dbFilter.filters
			origOrders = dbFilter.orders
			dbFilter = generateExpandoClass( skel.entityName+"_"+self.type+"_"+name ).query() #FIXME: Keys only!
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
			if not currentObj.entityName:
				return( rels )
			for key in dir( currentObj ):
				if key.startswith("__"):
					continue
				bone = getattr( currentObj, key )
				if isinstance( bone, relationalBone ):
					if not bone.type in rels.keys():
						rels[ bone.type ] = []
					data = ( currentObj.entityName, key, currentObj )
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

@PeriodicTask(60*60*24)
def updateRelations():
	from server import conf
	for modul, referers in findRelations( conf["viur.mainApp"] ).items():
		for entry in generateExpandoClass( modul ).query().filter( ndb.GenericProperty("viur_delayed_update_tag") > 0).iter():
			for refTable, refKey, skel in referers:
				oldRelations = generateExpandoClass( refTable+"_"+modul+"_"+refKey ).query()\
					.filter( ndb.GenericProperty("%s_id" % refKey ) == str( entry.key.urlsafe() ) )\
					.filter( ndb.GenericProperty("viur_delayed_update_tag") < entry.viur_delayed_update_tag  ).iter()
				for oldRelation in oldRelations:
					tmp = skel()
					tmp.fromDB( str(oldRelation.key.parent().urlsafe()) )
					for key in dir( tmp ):
						if not key.startswith("__") and isinstance( getattr( tmp, key ), relationalBone ):
							bone = getattr( tmp, key )
							if bone.value:
								if isinstance( bone.value, list ):
									bone.fromClient( [ x["id"] for x in bone.value] )
								else:
									bone.fromClient( bone.value["id"] )
					tmp.toDB( str(oldRelation.key.parent().urlsafe()), clearUpdateTag=True )
			tmp = entry.key.get() #Reset its modified tag
			tmp.viur_delayed_update_tag = 0
			tmp.put()

