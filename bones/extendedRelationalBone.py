# -*- coding: utf-8 -*-
from server.bones import baseBone
from server.bones.relationalBone import relationalBone
from server import db
from server.errors import ReadFromClientError
from server.utils import normalizeKey
from google.appengine.api import search
import json
from time import time
from datetime import datetime
import logging

class extendedRelationalBone( relationalBone ):
	"""
		This class extends a :class:`server.bones.relationalBone.relationalBone`, so that it can store
		additional properties along with the relation.

		This is only useful on multiple=True bones, as you could just store that properties in the
		containing skeleton.
	"""


	def __init__( self, type=None, module=None, refKeys=None, parentKeys=None, multiple=True, format="$(name)", using=None, *args, **kwargs):
		"""
			Initialize a new relationalBone.
			:param type: KindName of the referenced property.
			:type type: String
			:param module: Name of the modul which should be used to select entities of kind "type". If not set,
				the value of "type" will be used (the kindName must match the moduleName)
			:type type: String
			:param refKeys: A list of properties to include from the referenced property. These properties will be
				avaiable in the template without having to fetch the referenced property. Filtering is also only possible
				by properties named here!
			:type refKeys: List of Strings
			:param parentKeys: A list of properties from the current skeleton to include. If mixing filtering by
				relational properties and properties of the class itself, these must be named here.
			:type parentKeys: List of Strings
			:param multiple: If True, allow referencing multiple Elements of the given class. (Eg. n:n-relation.
				otherwise its n:1 )
			:type multiple: False
			:param format: Hint for the admin how to display such an relation. See admin/utils.py:formatString for
				more information
			:type format: String
		"""
		super( extendedRelationalBone, self ).__init__( type, module, refKeys, parentKeys, multiple, format, *args, **kwargs)
		if not multiple:
			raise ValueError("extendedRelationalBones must be multiple!")
		self.using = using


	def postSavedHandler( self, boneName, skel, key, dbfields ):
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
				if not dbObj[ "dest.key" ] in [ x["dest"]["key"] for x in values ]: #Relation has been removed
					db.Delete( dbObj.key() )
					continue
			except: #This entry is corrupt
				db.Delete( dbObj.key() )
			else: # Relation: Updated
				data = [x for x in values if x["dest"]["key"] == dbObj["dest.key"]][0]
				if self.indexed: #We dont store more than key and kinds, and these dont change
					#Write our (updated) values in
					for k, v in data["dest"].items():
						dbObj[ "dest."+k ] = v
					for k,v in parentValues.items():
						dbObj[ "src."+k ] = v
					for k, v in data["rel"].items():
						dbObj[ "rel."+k ] = v
					dbObj[ "viur_delayed_update_tag" ] = time()
					db.Put( dbObj )
				values.remove( data )

		# Add any new Relation
		for val in values:
			dbObj = db.Entity( "viur-relations" , parent=db.Key( key ) ) #skel.kindName+"_"+self.type+"_"+key

			if not self.indexed: #Dont store more than key and kinds, as they aren't used anyway
				dbObj[ "dest.key" ] = val["dest"]["key"]
				dbObj[ "src.key" ] = key
			else:
				for k, v in val["dest"].items():
					dbObj[ "dest."+k ] = v
				for k,v in parentValues.items():
					dbObj[ "src."+k ] = v
				for k, v in val["rel"].items():
					dbObj[ "rel."+k ] = v

			dbObj[ "viur_delayed_update_tag" ] = time()
			dbObj[ "viur_src_kind" ] = skel.kindName #The kind of the entry referencing
			#dbObj[ "viur_src_key" ] = str( key ) #The key of the entry referencing
			dbObj[ "viur_src_property" ] = boneName #The key of the bone referencing
			#dbObj[ "viur_dest_key" ] = val["key"]
			dbObj[ "viur_dest_kind" ] = self.type
			db.Put( dbObj )

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
			value = None
		self.value = []
		res = []
		tmpRes = {}
		for k,v in data.items():
			if k.startswith( name ):
				k = k.replace( name, "", 1)
				idx,bname = k.split(".")
				if not idx in tmpRes.keys():
					tmpRes[ idx ] = {}
				if bname in tmpRes[ idx ].keys():
					if isinstance( tmpRes[ idx ][bname], list ):
						tmpRes[ idx ][bname].append( v )
					else:
						tmpRes[ idx ][bname] = [ tmpRes[ idx ][bname], v ]
				else:
					tmpRes[ idx ][bname] = v
		tmpList = [ (k,v) for k,v in tmpRes.items() ]
		tmpList.sort( key=lambda k: k[0] )
		tmpList = [{"rel":v,"dest":{"key":v["key"]}} for k,v in tmpList]
		errorDict = {}
		for r in tmpList[:]:
			# Rebuild the referenced entity data
			isEntryFromBackup = False #If the referenced entry has been deleted, restore information from
			entry = None

			try:
				entry = db.Get( db.Key( r["dest"]["key"] ) )
			except: #Invalid key or something like that

				logging.info( "Invalid reference key >%s< detected on bone '%s'",
				              r["dest"]["key"], name )

				if isinstance(self._dbValue, dict):
					if self._dbValue["dest"]["key"]==str(r):
						entry = self._dbValue
						isEntryFromBackup = True
				elif  isinstance(self._dbValue, list):
					for dbVal in self._dbValue:


						if dbVal["dest"]["key"]==str(r):
							entry = dbVal
							isEntryFromBackup = True
				if not isEntryFromBackup:
					if not self.multiple: #We can stop here :/
						return( "Invalid entry selected" )
				else:
					tmpList.remove( r )
					continue
			if not entry or (not isEntryFromBackup and not entry.key().kind()==self.type): #Entry does not exist or has wrong type (is from another module)
				if entry:
					logging.error("I got a key, which kind doesn't match my type! (Got: %s, my type %s)" % ( entry.key().kind(), self.type ) )
				tmpList.remove( r )
				continue
			tmp = { k: entry[k] for k in entry.keys() if (k in self.refKeys or any( [ k.startswith("%s." %x) for x in self.refKeys ] ) ) }
			tmp["key"] = r["dest"]["key"]
			r["dest"] = tmp
			# Rebuild the refSkel data
			refSkel = self.using()
			if not refSkel.fromClient( r["rel"] ):
				for k,v in refSkel.errors.items():
					errorDict[ "%s.%s.%s" % (name,tmpList.index(r),k) ] = v
		self.value = tmpList
		if len( errorDict.keys() ):
			return( ReadFromClientError( errorDict, True ) )

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
						logging.warning( "Invalid filtering! Doing an relational Query on %s with multiple key= filters is unsupported!" % (name) )
						raise RuntimeError()
					if not isinstance(v, db.Key ):
						v = db.Key( v )
					dbFilter.ancestor( v )
					continue
				if not (k if not " " in k else k.split(" ")[0]) in self.parentKeys:
					logging.warning( "Invalid filtering! %s is not in parentKeys of RelationalBone %s!" % (k,name) )
					raise RuntimeError()
				dbFilter.filter( "src.%s" % k, v )
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
			if dbFilter.getKind()!="viur-relations":
				name, skel, dbFilter, rawFilter = self._rewriteQuery( name, skel, dbFilter, rawFilter )
			# Merge the relational filters in
			for key in myKeys:
				value = rawFilter[ key ]
				tmpdata = key.split("$")
				try:
					unused, _type, key = tmpdata[0].split(".")
					assert _type in ["dest","rel"]
				except:
					continue
				#Ensure that the relational-filter is in refKeys
				if _type=="dest" and not key in self.refKeys:
					logging.warning( "Invalid filtering! %s is not in refKeys of RelationalBone %s!" % (key,name) )
					raise RuntimeError()
				if _type=="rel" and not key in self.using().keys():
					logging.warning( "Invalid filtering! %s is not a bone in 'using' of %s" % (key,name) )
					raise RuntimeError()
				if len( tmpdata ) > 1:
					if tmpdata[1]=="lt":
						dbFilter.filter( "%s.%s <" % (_type,key), value )
					elif tmpdata[1]=="gt":
						dbFilter.filter( "%s.%s >" % (_type,key), value )
					elif tmpdata[1]=="lk":
						dbFilter.filter( "%s.%s >=" % (_type,key), value )
						dbFilter.filter( "%s.%s <" % (_type,key), value+u"\ufffd" )
					else:
						dbFilter.filter( "%s.%s =" % (_type,key), value )
				else:
					dbFilter.filter( "%s.%s =" % (_type,key), value )
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
			if not dbFilter.getKind()=="viur-relations": #This query has not been rewritten (yet)
				name, skel, dbFilter, rawFilter = self._rewriteQuery( name, skel, dbFilter, rawFilter )
			key = rawFilter["orderby"]
			try:
				unused, _type, param = key.split(".")
				assert _type in ["dest","rel"]
			except:
				return( dbFilter ) #We cant parse that
				#Ensure that the relational-filter is in refKeys
			if _type=="dest" and not param in self.refKeys:
				logging.warning( "Invalid filtering! %s is not in refKeys of RelationalBone %s!" % (param,name) )
				raise RuntimeError()
			if _type=="rel" and not param in self.using().keys():
				logging.warning( "Invalid filtering! %s is not a bone in 'using' of %s" % (param,name) )
				raise RuntimeError()
			if "orderdir" in rawFilter.keys()  and rawFilter["orderdir"]=="1":
				order = ( "%s.%s" % (_type,param), db.DESCENDING )
			else:
				order = ( "%s.%s" % (_type,param), db.ASCENDING )
			dbFilter = dbFilter.order( order )
			dbFilter.setFilterHook( lambda s, filter, value: self.filterHook( name, s, filter, value))
			dbFilter.setOrderHook( lambda s, orderings: self.orderHook( name, s, orderings))
		return( dbFilter )

	def getSearchDocumentFields(self, name): #FIXME
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

	def filterHook(self, name, query, param, value ): #FIXME
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
			if srcKey == "__key__": #Rewrite key= filter as its meaning has changed
				if isinstance( value, list ) or isinstance( value, tuple ):
					logging.warning( "Invalid filtering! Doing an relational Query on %s with multiple key= filters is unsupported!" % (name) )
					raise RuntimeError()
				if not isinstance( value, db.Key ):
					value = db.Key( value )
				query.ancestor( value )
				return( None )
			if not srcKey in self.parentKeys:
				logging.warning( "Invalid filtering! %s is not in parentKeys of RelationalBone %s!" % (srcKey,name) )
				raise RuntimeError()
			return( "src.%s" % param, value )

	def orderHook(self, name, query, orderings ): #FIXME
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
			if orderKey.startswith("dest.") or orderKey.startswith("rel.") or orderKey.startswith("src."):
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

	def refresh(self, boneName, skel):
		"""
			Refresh all values we might have cached from other entities.
		"""
		def updateInplace(valDict):
			"""
				Fetches the entity referenced by valDict["dest.key"] and updates all dest.* keys
				accordingly
			"""
			if not "dest" in valDict.keys():
				logging.error("Invalid dictionary in updateInplace: %s" % valDict)
				return False
				
			if "key" in valDict["dest"].keys():
				originalKey = valDict["dest"]["key"]
			# !!!ViUR re-design compatibility!!!
			elif "id" in valDict["dest"].keys():
				originalKey = valDict["dest"]["id"]
			else:
				logging.error("Invalid dictionary in updateInplace: %s" % valDict)
				return False

			entityKey = normalizeKey(originalKey)
			if originalKey != entityKey or not "key" in valDict["dest"].keys():
				logging.info("Rewriting %s to %s" % (originalKey, entityKey))
				valDict["dest"]["key"] = entityKey

			# Try to update referenced values;
			# If the entity does not exist with this key, ignore
			# (key was overidden above to have a new appid when transferred).
			try:
				newValues = db.Get(entityKey)
				assert newValues is not None
			except db.EntityNotFoundError:
				#This entity has been deleted
				logging.info("The key %s does not exist" % entityKey)
				return False
			except:
				raise

			for key in valDict["dest"].keys():
				if key in ["key", "id"]: # !!!ViUR re-design compatibility!!!
					continue
				elif key in newValues.keys():
					valDict["dest"][key] = newValues[key]

			return True

		if not self.value:
			return

		logging.info("Refreshing extendedRelationalBone %s of %s" % (boneName, skel.kindName))

		if isinstance( self.value, dict ):
			updateInplace(self.value)

		elif isinstance( self.value, list ):
			for k in self.value:
				updateInplace(k)
