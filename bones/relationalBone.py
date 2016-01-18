# -*- coding: utf-8 -*-
from server.bones import baseBone
from server import db
from google.appengine.api import search
import json
from time import time
from datetime import datetime
import logging
from server.utils import normalizeKey

class relationalBone( baseBone ):
	"""
		This is our magic class implementing relations.

		This implementation is read-efficient, e.g. filtering by relational-properties only costs an additional
		small-op for each entity returned.
		However, it costs several more write-ops for writing an entity to the db.
		(These costs are somewhat around additional (4+len(refKeys)+len(parentKeys)) write-ops for each referenced
		property) for multiple=True relationalBones and (4+len(refKeys)) for n:1 relations)

		So don't use this if you expect data being read less frequently than written! (Sorry, we don't have a
		write-efficient method yet)
		To speedup writes to (maybe) referenced entities, information in these relations isn't updated instantly.
		Once a skeleton is updated, a deferred task is kicked off which updates the references to
		that skeleton (if any).
		As a result, you might see stale data until this task has been finished.

		Example:
			* Entity A references Entity B.
			* Both have a property "name".
			* Entity B gets updated (it name changes).
			* As "A" has a copy of entity "B"s values, you'll see "B"s old name inside the values of the
			  relationalBone when fetching entity A.

		If you filter a list by relational properties, this will also use the old data! (Eg. filtering A's list by
		B's new name won't return any result)
	"""


	type = None
	module = None
	refKeys = ["key","name"]
	parentKeys = ["key","name"]

	@staticmethod
	def generageSearchWidget(target,module,name="RELATIONAL BONE"):
		return ( {"name":name,"target":target,"type":"relational","module":module} )

	def __init__( self, type=None, module=None, refKeys=None, parentKeys=None, multiple=False, format="$(name)",  *args,**kwargs):
		"""
			Initialize a new relationalBone.

			:param type: KindName of the referenced property.
			:type type: str
			:param module: Name of the modul which should be used to select entities of kind "type". If not set,
				the value of "type" will be used (the kindName must match the moduleName)
			:type type: str
			:param refKeys: A list of properties to include from the referenced property. These properties will be
				available in the template without having to fetch the referenced property. Filtering is also only possible
				by properties named here!
			:type refKeys: list<str>
			:param parentKeys: A list of properties from the current skeleton to include. If mixing filtering by
				relational properties and properties of the class itself, these must be named here.
			:type parentKeys: List of Strings
			:param multiple: If True, allow referencing multiple Elements of the given class. (Eg. n:n-relation.
				otherwise its n:1 )
			:type multiple: bool
			:param format: Hint for the admin how to display such an relation. See admin/utils.py:formatString for
				more information
			:type format: str
		"""
		baseBone.__init__( self, *args, **kwargs )
		self.multiple = multiple
		self.format = format
		self._dbValue = None #Store the original result fetched from the db here so we have that information in case a referenced entity has been deleted

		if type:
			self.type = type

		if module:
			self.module = module
		elif self.type:
			self.module = self.type

		if self.type is None or self.module is None:
			raise NotImplementedError("Type and Module of relationalbone's must not be None")

		if refKeys:
			if not "key" in refKeys:
				raise AttributeError("'key' must be included in refKeys!")
			self.refKeys=refKeys

		if parentKeys:
			if not "key" in parentKeys:
				raise AttributeError("'key' must be included in parentKeys!")
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
					try:
						self.value = json.loads( val[0] )
					except:
						pass
				else:
					if val:
						try:
							self.value = json.loads( val )
						except:
							pass
					else:
						self.value = None

		else:
			self.value = None
		if isinstance( self.value, list ):
			self._dbValue = self.value[ : ]
		elif isinstance( self.value, dict ):
			self._dbValue = dict( self.value.items() )
		else:
			self._dbValue = None
		return( True )
	
	def serialize(self, name, entity ):
		if not self.value:
			entity.set( name, None, False )
			if not self.multiple:
				for k in entity.keys():
					if k.startswith("%s." % name):
						del entity[ k ]
		else:
			if self.multiple:
				res = []
				for val in self.value:
					res.append( json.dumps( val ) )
				entity.set( name, res, False )
			else:
				entity.set( name, json.dumps( self.value ), False )
				#Copy attrs of our referenced entity in
				if self.indexed:
					for k, v in self.value.items():
						if (k in self.refKeys or any( [ k.startswith("%s." %x) for x in self.refKeys ] ) ):
							entity[ "%s.%s" % (name,k) ] = v
		return( entity )
	
	def postSavedHandler( self, boneName, skel, key, dbfields ):
		def isIndexable( val ):
			if isinstance( val, unicode ) or isinstance(val, str):
				if len( val )>=500:
					return( False )
			if isinstance( val, list ):
				for x in val:
					if isinstance( x, unicode ) or isinstance( x, str ):
						if( len( x )>= 500 ):
							return( False )
			return( True )
		if not self.value:
			values = []
		elif isinstance( self.value, dict ):
			values = [ dict( (k,v) for k,v in self.value.items() ) ]
		else:
			values = [ dict( (k,v) for k,v in x.items() ) for x in self.value ]
		parentValues = {}
		for parentKey in self.parentKeys:
			if parentKey in dbfields.keys():
				parentValues[ parentKey ] = dbfields[ parentKey ]

		dbVals = db.Query( "viur-relations" ).ancestor( db.Key( key ) ) #skel.kindName+"_"+self.type+"_"+key
		dbVals.filter("viur_src_kind =", skel.kindName )
		dbVals.filter("viur_dest_kind =", self.type )
		dbVals.filter("viur_src_property =", boneName )
		for dbObj in dbVals.iter():
			try:
				if not dbObj[ "dest.key" ] in [ x["key"] for x in values ]: #Relation has been removed
					db.Delete( dbObj.key() )
					continue
			except: #This entry is corrupt
				db.Delete( dbObj.key() )
			else: # Relation: Updated
				data = [ x for x in values if x["key"] == dbObj[ "dest.key" ] ][0]
				if self.multiple and self.indexed: #We dont store more than key and kinds, and these dont change
					for k,v in parentValues.items(): #Write our (updated) values in
						if not isIndexable(v):
							dbObj[ "src."+k ] = None
							logging.error("Cannot index property src.%s of relationalBone %s" % (k,boneName))
						else:
							dbObj[ "src."+k ] = v
					for k, v in data.items():
						if not isIndexable(v):
							dbObj[ "dest."+k ] = None
							logging.error("Cannot index property dest.%s of relationalBone %s" % (k,boneName))
						else:
							dbObj[ "dest."+k ] = v
					dbObj[ "viur_delayed_update_tag" ] = time()
					db.Put( dbObj )
				values.remove( data )
		# Add any new Relation
		for val in values:
			dbObj = db.Entity( "viur-relations" , parent=db.Key( key ) ) #skel.kindName+"_"+self.type+"_"+key
			if not self.multiple or not self.indexed: #Dont store more than key and kinds, as they aren't used anyway
				dbObj[ "dest.key" ] = val["key"]
				dbObj[ "src.key" ] = key
			else:
				for k, v in val.items():
					if not isIndexable(v):
						dbObj[ "dest."+k ] = None
						logging.error("Cannot index property dest.%s of relationalBone %s" % (k,boneName))
					else:
						dbObj[ "dest."+k ] = v
				for k,v in parentValues.items():
					if not isIndexable(v):
						dbObj[ "src."+k ] = None
						logging.error("Cannot index property src.%s of relationalBone %s" % (k,boneName))
					else:
						dbObj[ "src."+k ] = v
			dbObj[ "viur_delayed_update_tag" ] = time()
			dbObj[ "viur_src_kind" ] = skel.kindName #The kind of the entry referencing
			#dbObj[ "viur_src_key" ] = str( id ) #The id of the entry referencing
			dbObj[ "viur_src_property" ] = boneName #The key of the bone referencing
			#dbObj[ "viur_dest_key" ] = val[ "key" ]
			dbObj[ "viur_dest_kind" ] = self.type
			db.Put( dbObj )
		
	def postDeletedHandler( self, skel, key, id ):
		db.Delete( [x for x in db.Query( "viur-relations" ).ancestor( db.Key( id ) ).run( keysOnly=True ) ] ) #skel.kindName+"_"+self.type+"_"+key
	
	def rebuildData(self, *args, **kwargs ):
		pass
	
	def isInvalid( self, id ):
		return( True )
	

	def fromClient( self, name, data ):
		"""
			Reads a value from the client.
			If this value is valid for this bone,
			store this value and return None.
			Otherwise our previous value is
			left unchanged and an error-message
			is returned.
			
			:param name: Our name in the skeleton
			:type name: String
			:param data: *User-supplied* request-data
			:type data: Dict
			:returns: None or String
		"""
		if name in data.keys():
			value = data[ name ]
		else:
			value = []
			for k,v in data.items():
				if k.startswith( name ):
					k = k.replace( name, "", 1)
					try:
						idx = int(k)
					except:
						continue
					value.insert(idx, v)
			if len(value)==0:
				value = None
			elif len(value)==1:
				value = value[1]
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
							if valstr and self.isInvalid(  valstr  ):
								res.append(  valstr )
					else:
						valstr =  value
						if valstr and self.isInvalid(  valstr ):
							res.append( valstr )
			else:
				for val in value:
					valstr =  val 
					if valstr and self.isInvalid( valstr  ):
						res.append( valstr )
		else:
			valstr = value 
			if valstr and self.isInvalid( valstr ):
				res.append( valstr )
		
		if len( res ) == 0:
			return( "No value entered" )
		for r in res:
			isEntryFromBackup = False #If the referenced entry has been deleted, restore information from 
			try:
				entry = db.Get( db.Key( r ) )
			except: #Invalid key or something like that
				if isinstance(self._dbValue, dict):
					if normalizeKey(self._dbValue["key"])==normalizeKey(r):
						entry = self._dbValue
						isEntryFromBackup = True
				elif  isinstance(self._dbValue, list):
					for dbVal in self._dbValue:
						if normalizeKey(dbVal["key"])==normalizeKey(r):
							entry = dbVal
							isEntryFromBackup = True
				if not isEntryFromBackup:
					if not self.multiple: #We can stop here :/
						return( "Invalid entry selected" )
					else:
						continue
			if not entry or (not isEntryFromBackup and not entry.key().kind()==self.type): #Entry does not exist or has wrong type (is from another module)
				if entry:
					logging.error("I got an id, which kind doesn't match my type! (Got: %s, my type %s)" % ( entry.key().kind(), self.type ) )
				continue
			if not self.multiple:
				self.value = { k: entry[k] for k in entry.keys() if (k in self.refKeys or any( [ k.startswith("%s." %x) for x in self.refKeys ] ) ) }
				self.value["key"] = r
				return( None )
			else:
				tmp = { k: entry[k] for k in entry.keys() if (k in self.refKeys or any( [ k.startswith("%s." %x) for x in self.refKeys ] ) ) }
				tmp["key"] = r
				self.value.append( tmp )
		if not self.value:
			return( "No value entered" )
		return( None )

	def _rewriteQuery(self, name, skel, dbFilter, rawFilter ):
		"""
			Rewrites a datastore query to operate on "viur-relations" instead of the original kind.
			This is needed to perform relational queries on n:m relations.
		"""
		origFilter = dbFilter.datastoreQuery
		origSortOrders = dbFilter.getOrders()

		if isinstance( origFilter, db.MultiQuery):
			raise NotImplementedError("Doing a relational Query with multiple=True and \"IN or !=\"-filters is currently unsupported!")

		dbFilter.datastoreQuery = type( dbFilter.datastoreQuery )( "viur-relations" ) #skel.kindName+"_"+self.type+"_"+name
		dbFilter.filter("viur_src_kind =", skel.kindName )
		dbFilter.filter("viur_dest_kind =", self.type )
		dbFilter.filter("viur_src_property", name )

		if dbFilter._origCursor: #Merge the cursor in again (if any)
			dbFilter.cursor( dbFilter._origCursor )

		if origFilter:
			for k,v in origFilter.items(): #Merge old filters in
				#Ensure that all non-relational-filters are in parentKeys
				if k=="__key__":
					# We must process the key-property separately as its meaning changes as we change the datastore kind were querying
					if isinstance( v, list ) or isinstance(v, tuple):
						logging.warning( "Invalid filtering! Doing an relational Query on %s with multiple id= filters is unsupported!" % (name) )
						raise RuntimeError()
					if not isinstance(v, db.Key ):
						v = db.Key( v )
					dbFilter.ancestor( v )
					continue
				if not (k if not " " in k else k.split(" ")[0]) in self.parentKeys:
					logging.warning( "Invalid filtering! %s is not in parentKeys of RelationalBone %s!" % (k,name) )
					raise RuntimeError()
				dbFilter.filter( "src.%s" % k, v )

		# Take original sort order
		orderList = []
		for k,d in origSortOrders: #Merge old sort orders in
			if not k in self.parentKeys:
				logging.warning( "Invalid filtering! %s is not in parentKeys of RelationalBone %s!" % (k,name) )
				raise RuntimeError()

			orderList.append( ("src.%s" % k, d) )

		if orderList:
			dbFilter.order( *orderList )

		return( name, skel, dbFilter, rawFilter )

	def buildDBFilter( self, name, skel, dbFilter, rawFilter ):
		origFilter = dbFilter.datastoreQuery
		if origFilter is None:  #This query is unsatisfiable
			return( dbFilter )
		myKeys = [ x for x in rawFilter.keys() if x.startswith( "%s." % name ) ]
		if len( myKeys ) > 0 and not self.indexed:
			logging.warning( "Invalid searchfilter! %s is not indexed!" % name )
			raise RuntimeError()
		if len( myKeys ) > 0: #We filter by some properties
			if self.multiple: #We have a n:m relation, so we
				# create a new Filter based on our SubType and copy the parameters
				if dbFilter.getKind()!="viur-relations":
					name, skel, dbFilter, rawFilter = self._rewriteQuery( name, skel, dbFilter, rawFilter )
			# Merge the relational filters in
			for key in myKeys:
				value = rawFilter[ key ]
				tmpdata = key.split("$")
				key = tmpdata[0].split(".")[1]
				#Ensure that the relational-filter is in refKeys
				if not key in self.refKeys:
					logging.warning( "Invalid filtering! %s is not in refKeys of RelationalBone %s!" % (key,name) )
					raise RuntimeError()
				if len( tmpdata ) > 1:
					if tmpdata[1]=="lt":
						if self.multiple:
							dbFilter.filter( "dest.%s <" % key, value )
						else:
							dbFilter.filter( "%s.%s <" % (name, key), value )
					elif tmpdata[1]=="gt":
						if self.multiple:
							dbFilter.filter( "dest.%s >" % key, value )
						else:
							dbFilter.filter( "%s.%s >" % (name, key), value )
					else:
						if self.multiple:
							dbFilter.filter( "dest.%s =" % key, value )
						else:
							dbFilter.filter( "%s.%s =" % (name, key), value )
				else:
					if self.multiple:
						if isinstance( value, list ):
							dbFilter.filter( "dest.%s IN" % key, value )
						else:
							dbFilter.filter( "dest.%s =" % key, value )
					else:
						if isinstance( value, list):
							dbFilter.filter( "%s.%s IN" % (name, key), value )
						else:
							dbFilter.filter( "%s.%s =" % (name, key), value )
			dbFilter.setFilterHook( lambda s, filter, value: self.filterHook( name, s, filter, value))
			dbFilter.setOrderHook( lambda s, orderings: self.orderHook( name, s, orderings) )
		elif name in rawFilter.keys() and rawFilter[ name ].lower()=="none":
			dbFilter = dbFilter.filter( "%s =" % name, None )
		return( dbFilter )

	def buildDBSort( self, name, skel, dbFilter, rawFilter ):
		origFilter = dbFilter.datastoreQuery
		if origFilter is None or not "orderby" in rawFilter.keys(): #This query is unsatisfiable or not sorted
			return( dbFilter )
		if "orderby" in list(rawFilter.keys()) and isinstance(rawFilter["orderby"], basestring) and rawFilter["orderby"].startswith( "%s." % name ):
			if self.multiple:
				if not dbFilter.getKind()=="viur-relations": #This query has not been rewritten (yet)
					name, skel, dbFilter, rawFilter = self._rewriteQuery( name, skel, dbFilter, rawFilter )
				key = rawFilter["orderby"]
				param = key.split(".")[1]
				if not param in self.refKeys:
					logging.warning( "Invalid ordering! %s is not in refKeys of RelationalBone %s!" % (param,name) )
					raise RuntimeError()
				if "orderdir" in rawFilter.keys()  and rawFilter["orderdir"]=="1":
					order = ( "dest."+param, db.DESCENDING )
				else:
					order = ( "dest."+param, db.ASCENDING )
				dbFilter = dbFilter.order( order )
				dbFilter.setFilterHook( lambda s, filter, value: self.filterHook( name, s, filter, value))
				dbFilter.setOrderHook( lambda s, orderings: self.orderHook( name, s, orderings))
			else: #Not multiple
				key = rawFilter["orderby"]
				param = key.split(".")[1]
				if not param in self.refKeys:
					logging.warning( "Invalid ordering! %s is not in refKeys of RelationalBone %s!" % (param,name) )
					raise RuntimeError()
				if "orderdir" in rawFilter.keys()  and rawFilter["orderdir"]=="1":
					order = ( "%s.%s" % (name,param), db.DESCENDING )
				else:
					order = ( "%s.%s"% (name,param), db.ASCENDING )
				dbFilter = dbFilter.order( order )
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
				res.append( search.TextField( name=( "%s_%s" % (name, k) ).replace(".", "_"), value=unicode( v ) ) )
		return( res )

	def filterHook(self, name, query, param, value ):
		"""
			Hook installed by buildDbFilter.
			This rewrites all filters added to the query after buildDbFilter has been run to match the
			layout of our viur-relations index.
			Also performs sanity checks wherever this query is possible at all.
		"""
		if param.startswith("src.") or param.startswith("dest.") or param.startswith("viur_"):
			#This filter is already valid in our relation
			return( param, value )
		if param.startswith( "%s." % name):
			#We add a constrain filtering by properties of the referenced entity
			refKey = param.replace( "%s." % name, "" )
			if " " in refKey: #Strip >, < or = params
				refKey = refKey[ :refKey.find(" ")]
			if not refKey in self.refKeys:
				logging.warning( "Invalid filtering! %s is not in refKeys of RelationalBone %s!" % (refKey,name) )
				raise RuntimeError()
			if self.multiple:
				return( param.replace( "%s." % name, "dest."), value )
			else:
				return( param, value )
		else:
			#We filter by a property of this entity
			if not self.multiple:
				#Not relational, not multiple - nothing to do here
				return( param, value )
			#Prepend "src."
			srcKey = param
			if " " in srcKey:
				srcKey = srcKey[ : srcKey.find(" ")] #Cut <, >, and =
			if srcKey == "__key__": #Rewrite id= filter as its meaning has changed
				if isinstance( value, list ) or isinstance( value, tuple ):
					logging.warning( "Invalid filtering! Doing an relational Query on %s with multiple id= filters is unsupported!" % (name) )
					raise RuntimeError()
				if not isinstance( value, db.Key ):
					value = db.Key( value )
				query.ancestor( value )
				return( None )
			if not srcKey in self.parentKeys:
				logging.warning( "Invalid filtering! %s is not in parentKeys of RelationalBone %s!" % (srcKey,name) )
				raise RuntimeError()
			return( "src.%s" % param, value )

	def orderHook(self, name, query, orderings ):
		"""
			Hook installed by buildDbFilter.
			This rewrites all orderings added to the query after buildDbFilter has been run to match the
			layout of our viur-relations index.
			Also performs sanity checks wherever this query is possible at all.
		"""
		res = []
		if not isinstance( orderings, list) and not isinstance( orderings, tuple):
			orderings = [ orderings ]
		for order in orderings:
			if isinstance( order, tuple):
				orderKey = order[0]
			else:
				orderKey = order
			if orderKey.startswith("dest.") or orderKey.startswith("src."):
				#This is already valid for our relational index
				res.append( order )
				continue
			if orderKey.startswith("%s." % name ):
				k = orderKey.replace( "%s." % name, "" )
				if not k in self.refKeys:
					logging.warning( "Invalid ordering! %s is not in refKeys of RelationalBone %s!" % (k,name) )
					raise RuntimeError()
				if not self.multiple:
					res.append( order )
				else:
					if isinstance( order, tuple ):
						res.append( ("dest.%s" % k, order[1] ) )
					else:
						res.append( "dest.%s" % k )
			else:
				if not self.multiple:
					# Nothing to do here
					res.append( order )
					continue
				else:
					if not orderKey in self.parentKeys:
						logging.warning( "Invalid ordering! %s is not in parentKeys of RelationalBone %s!" % (orderKey,name) )
						raise RuntimeError()
					if isinstance( order, tuple ):
						res.append( ("src.%s" % orderKey, order[1] ) )
					else:
						res.append( "src.%s" % orderKey )
		return( res )

	def refresh(self, boneName, skel ):
		"""
			Refresh all values we might have cached from other entities.
		"""
		logging.warning("Refreshing Relationalbone %s of %s" % (boneName, skel.kindName))
		if not self.value:
			return
		if isinstance( self.value, dict ) and "key" in self.value.keys():
			# Try fixing
			self.fromClient( boneName, {boneName: normalizeKey(self.value["key"])} )
		elif isinstance( self.value, list ):
			tmpList = []
			for data in self.value:
				if isinstance(data,dict) and "key" in data.keys():
					tmpList.append( normalizeKey(data["key"]) )
			self.fromClient( boneName, {boneName: tmpList} )
