# -*- coding: utf-8 -*-
from server.bones import baseBone
from server.bones.bone import getSystemInitialized
from server import db
from server.errors import ReadFromClientError
from server.utils import normalizeKey
from google.appengine.api import search
import extjson
from time import time
from datetime import datetime
import logging


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
	refKeys = ["key", "name"]
	parentKeys = ["key", "name"]
	type = "relational"
	kind = None

	def __init__(self, kind=None, module=None, refKeys=None, parentKeys=None, multiple=False,
	             format="$(dest.name)", using=None, *args, **kwargs):
		"""
			Initialize a new relationalBone.

			:param kind: KindName of the referenced property.
			:type kind: String
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
		baseBone.__init__( self, *args, **kwargs )
		self.multiple = multiple
		self.format = format
		#self._dbValue = None #Store the original result fetched from the db here so we have that information in case a referenced entity has been deleted

		if kind:
			self.kind = kind

		if module:
			self.module = module
		elif self.kind:
			self.module = self.kind

		if self.kind is None or self.module is None:
			raise NotImplementedError("Type and Module of relationalbone's must not be None")

		if refKeys:
			if not "key" in refKeys:
				raise AttributeError("'key' must be included in refKeys!")
			self.refKeys = refKeys

		if parentKeys:
			if not "key" in parentKeys:
				raise AttributeError("'key' must be included in parentKeys!")
			self.parentKeys=parentKeys

		self.using = using

		if getSystemInitialized():
			from server.skeleton import RefSkel, skeletonByKind
			self._refSkelCache = RefSkel.fromSkel(skeletonByKind(self.kind), *self.refKeys)
			self._usingSkelCache = using() if using else None
		else:
			self._refSkelCache = None
			self._usingSkelCache = None



	def setSystemInitialized(self):
		super(relationalBone, self).setSystemInitialized()
		from server.skeleton import RefSkel, skeletonByKind
		self._refSkelCache = RefSkel.fromSkel(skeletonByKind(self.kind), *self.refKeys)
		self._usingSkelCache = self.using() if self.using else None


	def _restoreValueFromDatastore(self, val):
		"""
			Restores one of our values (including the Rel- and Using-Skel) from the serialized data read from the datastore
			:param value: Json-Encoded datastore property
			:return: Our Value (with restored RelSkel and using-Skel)
		"""
		value = extjson.loads(val)
		assert isinstance(value, dict), "Read something from the datastore thats not a dict: %s" % str(type(value))

		relSkel = self._refSkelCache
		relSkel.setValuesCache({})

		# !!!ViUR re-design compatibility!!!
		if not "dest" in value:
			nvalue = dict()
			nvalue["dest"] = value
			value = nvalue

		if "id" in value["dest"] and not("key" in value["dest"] and value["dest"]["key"]):
			value["dest"]["key"] = value["dest"]["id"]
			del value["dest"]["id"]
		# UNTIL HERE!

		relSkel.unserialize(value["dest"])

		if self.using is not None:
			usingSkel = self._usingSkelCache
			usingSkel.setValuesCache({})
			if value["rel"] is not None:
				usingSkel.unserialize(value["rel"])
			usingData = usingSkel.getValuesCache()
		else:
			usingData = None
		return {"dest": relSkel.getValuesCache(), "rel": usingData}


	def unserialize( self, valuesCache, name, expando ):
		if name in expando:
			val = expando[ name ]
			if self.multiple:
				valuesCache[name] = []
				if not val:
					return True
				if isinstance(val, list):
					for res in val:
						try:
							valuesCache[name].append(self._restoreValueFromDatastore(res))
						except:
							raise
							pass
				else:
					try:
						valuesCache[name].append(self._restoreValueFromDatastore(val))
					except:
						raise
						pass
			else:
				valuesCache[name] = None
				if isinstance( val, list ) and len( val )>0:
					try:
						valuesCache[name] = self._restoreValueFromDatastore(val[0])
					except:
						raise
						pass
				else:
					if val:
						try:
							valuesCache[name] = self._restoreValueFromDatastore(val)
						except:
							raise
							pass
					else:
						valuesCache[name] = None
		else:
			valuesCache[name] = None
		#if isinstance( valuesCache[name], list ):
		#	self._dbValue = valuesCache[name][ : ]
		#elif isinstance( valuesCache[name], dict ):
		#	self._dbValue = dict( valuesCache[name].items() )
		#else:
		#	self._dbValue = None
		return True

	def serialize(self, valuesCache, name, entity ):
		if not valuesCache[name]:
			entity.set( name, None, False )
			if not self.multiple:
				for k in entity.keys():
					if k.startswith("%s." % name):
						del entity[ k ]
		else:
			if self.multiple:
				res = []
				refSkel = self._refSkelCache
				usingSkel = self._usingSkelCache
				for val in valuesCache[name]:
					if val["dest"]:
						refSkel.setValuesCache(val["dest"])
						refData = refSkel.serialize()
					else:
						refData = None
					if usingSkel and val["rel"]:
						usingSkel.setValuesCache(val["rel"])
						usingData = usingSkel.serialize()
					else:
						usingData = None
					r = {"rel": usingData, "dest": refData}
					res.append(extjson.dumps(r))
				entity.set( name, res, False )
			else:
				refSkel = self._refSkelCache
				usingSkel = self._usingSkelCache
				if valuesCache[name]["dest"]:
					refSkel.setValuesCache(valuesCache[name]["dest"])
					refData = refSkel.serialize()
				else:
					refData = None
				if usingSkel and valuesCache[name]["rel"]:
					usingSkel.setValuesCache(valuesCache[name]["rel"])
					usingData = usingSkel.serialize()
				else:
					usingData = None
				r = {"rel": usingData, "dest": refData}
				entity.set(name, extjson.dumps(r), False)
				#Copy attrs of our referenced entity in
				if self.indexed:
					if refData:
						for k, v in refData.items():
							entity[ "%s.dest.%s" % (name,k) ] = v
					if usingData:
						for k, v in usingData.items():
							entity[ "%s.rel.%s" % (name,k) ] = v
					#for k, v in valuesCache[name].items():
					#	if (k in self.refKeys or any( [ k.startswith("%s." %x) for x in self.refKeys ] ) ):
					#		entity[ "%s.%s" % (name,k) ] = v
		return entity

	def postSavedHandler( self, valuesCache, boneName, skel, key, dbfields ):
		if not valuesCache[boneName]:
			values = []
		elif isinstance( valuesCache[boneName], dict ):
			values = [ dict( (k,v) for k,v in valuesCache[boneName].items() ) ]
		else:
			values = [ dict( (k,v) for k,v in x.items() ) for x in valuesCache[boneName] ]

		parentValues = {}

		for parentKey in self.parentKeys:
			if parentKey in dbfields:
				parentValues[ parentKey ] = dbfields[ parentKey ]

		dbVals = db.Query( "viur-relations" ).ancestor( db.Key( key ) ) #skel.kindName+"_"+self.kind+"_"+key
		dbVals.filter("viur_src_kind =", skel.kindName )
		dbVals.filter("viur_dest_kind =", self.kind)
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
					refSkel = self._refSkelCache
					refSkel.setValuesCache(data["dest"])
					for k, v in refSkel.serialize().items():
						dbObj[ "dest."+k ] = v
					for k,v in parentValues.items():
						dbObj[ "src."+k ] = v
					if self.using is not None:
						usingSkel = self._usingSkelCache
						usingSkel.setValuesCache(data["rel"])
						for k, v in usingSkel.serialize().items():
							dbObj[ "rel."+k ] = v
					dbObj[ "viur_delayed_update_tag" ] = time()
					db.Put( dbObj )
				values.remove( data )

		# Add any new Relation
		for val in values:
			dbObj = db.Entity( "viur-relations" , parent=db.Key( key ) ) #skel.kindName+"_"+self.kind+"_"+key

			if not self.indexed: #Dont store more than key and kinds, as they aren't used anyway
				dbObj[ "dest.key" ] = val["dest"]["key"]
				dbObj[ "src.key" ] = key
			else:
				refSkel = self._refSkelCache
				refSkel.setValuesCache(val["dest"])
				for k, v in refSkel.serialize().items():
					dbObj[ "dest."+k ] = v
				for k,v in parentValues.items():
					dbObj[ "src."+k ] = v
				if self.using is not None:
					usingSkel = self._usingSkelCache
					usingSkel.setValuesCache(val["rel"])
					for k, v in usingSkel.serialize().items():
						dbObj[ "rel."+k ] = v

			dbObj[ "viur_delayed_update_tag" ] = time()
			dbObj[ "viur_src_kind" ] = skel.kindName #The kind of the entry referencing
			#dbObj[ "viur_src_key" ] = str( key ) #The key of the entry referencing
			dbObj[ "viur_src_property" ] = boneName #The key of the bone referencing
			#dbObj[ "viur_dest_key" ] = val["key"]
			dbObj[ "viur_dest_kind" ] = self.kind
			db.Put( dbObj )

	def postDeletedHandler( self, skel, key, id ):
		db.Delete( [x for x in db.Query( "viur-relations" ).ancestor( db.Key( id ) ).run( keysOnly=True ) ] )

	def isInvalid( self, key ):
		return False

	def fromClient( self, valuesCache, name, data ):
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
		#from server.skeleton import RefSkel, skeletonByKind

		oldValues = valuesCache.get(name, None)
		valuesCache[name] = []
		tmpRes = {}

		clientPrefix = "%s." % name

		for k, v in data.items():
			if k.startswith(clientPrefix) or k == name:
				if k == name:
					k = k.replace(name, "", 1)
				else:
					k = k.replace(clientPrefix, "", 1)

				if "." in k:
					try:
						idx, bname = k.split(".", 1)
						idx = int(idx)
					except ValueError:
						# We got some garbarge as input; don't try to parse it
						continue

				elif k.isdigit() and self.using is None:
					idx = int(k)
					bname = "key"
				elif self.using is None and not self.multiple:
					idx = 0
					bname = "key"
				else:
					continue

				if not idx in tmpRes:
					tmpRes[ idx ] = {}

				if bname in tmpRes[ idx ]:
					if isinstance( tmpRes[ idx ][bname], list ):
						tmpRes[ idx ][bname].append( v )
					else:
						tmpRes[ idx ][bname] = [ tmpRes[ idx ][bname], v ]
				else:
					tmpRes[ idx ][bname] = v

		tmpList = [(k,v) for k,v in tmpRes.items() if "key" in v]
		tmpList.sort( key=lambda k: k[0] )
		tmpList = [{"reltmp":v,"dest":{"key":v["key"]}} for k,v in tmpList]
		errorDict = {}
		forceFail = False
		if not tmpList and self.required:
			return "No value selected!"
		for r in tmpList[:]:
			# Rebuild the referenced entity data
			isEntryFromBackup = False #If the referenced entry has been deleted, restore information from
			entry = None

			try:
				entry = db.Get( db.Key( r["dest"]["key"] ) )
			except: #Invalid key or something like thatmnn

				logging.info( "Invalid reference key >%s< detected on bone '%s'",
							  r["dest"]["key"], name )
				if isinstance(oldValues, dict):
					if oldValues["dest"]["key"]==str(r["dest"]["key"]):
						refSkel = self._refSkelCache
						refSkel.setValuesCache(oldValues["dest"])
						entry = refSkel.serialize()
						isEntryFromBackup = True
				elif isinstance(oldValues, list):
					for dbVal in oldValues:
						if dbVal["dest"]["key"]==str(r["dest"]["key"]):
							refSkel = self._refSkelCache
							refSkel.setValuesCache(dbVal["dest"])
							entry = refSkel.serialize()
							isEntryFromBackup = True
				if not isEntryFromBackup:
					if not self.multiple: #We can stop here :/
						return( "Invalid entry selected" )
					else:
						tmpList.remove(r)
						continue

			if not entry or (not isEntryFromBackup and not entry.key().kind()==self.kind): #Entry does not exist or has wrong type (is from another module)
				if entry:
					logging.error("I got a key, which kind doesn't match my type! (Got: %s, my type %s)" % ( entry.key().kind(), self.kind))
				tmpList.remove(r)
				continue

			tmp = { k: entry[k] for k in entry.keys() if (k in self.refKeys or any( [ k.startswith("%s." %x) for x in self.refKeys ] ) ) }
			tmp["key"] = r["dest"]["key"]
			relSkel = self._refSkelCache
			relSkel.setValuesCache({})
			relSkel.unserialize(tmp)
			r["dest"] = relSkel.getValuesCache()

			# Rebuild the refSkel data
			if self.using is not None:
				refSkel = self._usingSkelCache
				refSkel.setValuesCache({})
				if not refSkel.fromClient( r["reltmp"] ):
					for k,v in refSkel.errors.items():
						errorDict[ "%s.%s.%s" % (name,tmpList.index(r),k) ] = v
						forceFail = True
				r["rel"] = refSkel.getValuesCache()
			else:
				r["rel"] = None
			del r["reltmp"]

		if self.multiple:
			cleanList = []
			for item in tmpList:
				err = self.isInvalid(item)
				if err:
					errorDict["%s.%s" % (name, tmpList.index(item))] = err
				else:
					cleanList.append(item)
			if not cleanList:
				errorDict[name] = "No value selected"
			valuesCache[name] = tmpList
		else:
			if tmpList:
				val = tmpList[0]
			else:
				val = None
			err = self.isInvalid(val)
			if not err:
				valuesCache[name] = val
				if val is None:
					errorDict[name] = "No value selected"
		if len(errorDict.keys()):
			return ReadFromClientError(errorDict, forceFail)

	def _rewriteQuery(self, name, skel, dbFilter, rawFilter ):
		"""
			Rewrites a datastore query to operate on "viur-relations" instead of the original kind.
			This is needed to perform relational queries on n:m relations.
		"""
		origFilter = dbFilter.datastoreQuery
		origSortOrders = dbFilter.getOrders()
		if isinstance( origFilter, db.MultiQuery):
			raise NotImplementedError("Doing a relational Query with multiple=True and \"IN or !=\"-filters is currently unsupported!")
		dbFilter.datastoreQuery = type( dbFilter.datastoreQuery )( "viur-relations" ) #skel.kindName+"_"+self.kind+"_"+name
		dbFilter.filter("viur_src_kind =", skel.kindName )
		dbFilter.filter("viur_dest_kind =", self.kind)
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
				if not (k if " " not in k else k.split(" ")[0]) in self.parentKeys:
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

	def buildDBFilter( self, name, skel, dbFilter, rawFilter, prefix=None ):
		from server.skeleton import RefSkel, skeletonByKind
		origFilter = dbFilter.datastoreQuery

		if origFilter is None:  #This query is unsatisfiable
			return( dbFilter )

		myKeys = [ x for x in rawFilter.keys() if x.startswith( "%s." % name ) ]

		if len( myKeys ) > 0 and not self.indexed:
			logging.warning( "Invalid searchfilter! %s is not indexed!" % name )
			raise RuntimeError()

		if len( myKeys ) > 0: #We filter by some properties

			if dbFilter.getKind()!="viur-relations" and self.multiple:
				name, skel, dbFilter, rawFilter = self._rewriteQuery( name, skel, dbFilter, rawFilter )

			relSkel = RefSkel.fromSkel(skeletonByKind(self.kind), *self.refKeys)

			# Merge the relational filters in
			for myKey in myKeys:
				value = rawFilter[ myKey ]

				try:
					unused, _type, key = myKey.split(".",2)
					assert _type in ["dest","rel"]
				except:
					if self.using is None:
						# This will be a "dest" query
						_type = "dest"
						try:
							unused, key = myKey.split(".", 1)
						except:
							continue
					else:
						continue

				# just use the first part of "key" to check against our refSkel / relSkel (strip any leading .something and $something)
				checkKey = key
				if "." in checkKey:
					checkKey = checkKey.split(".")[0]

				if "$" in checkKey:
					checkKey = checkKey.split("$")[0]

				if _type=="dest":

					#Ensure that the relational-filter is in refKeys
					if checkKey not in self.refKeys:
						logging.warning( "Invalid filtering! %s is not in refKeys of RelationalBone %s!" % (key,name) )
						raise RuntimeError()

					# Iterate our relSkel and let these bones write their filters in
					for bname, bone in relSkel.items():
						if checkKey == bname:
							newFilter = {key: value}
							if self.multiple:
								bone.buildDBFilter(bname, relSkel, dbFilter, newFilter, prefix=(prefix or "")+"dest.")
							else:
								bone.buildDBFilter(bname, relSkel, dbFilter, newFilter, prefix=(prefix or "")+name+".dest.")

				elif _type=="rel":

					#Ensure that the relational-filter is in refKeys
					if self.using is None or checkKey not in self.using():
						logging.warning( "Invalid filtering! %s is not a bone in 'using' of %s" % (key,name) )
						raise RuntimeError()

					# Iterate our usingSkel and let these bones write their filters in
					for bname, bone in self.using().items():
						if key.startswith(bname):
							newFilter = {key: value}
							if self.multiple:
								bone.buildDBFilter(bname, relSkel, dbFilter, newFilter, prefix=(prefix or "")+"rel.")
							else:
								bone.buildDBFilter(bname, relSkel, dbFilter, newFilter, prefix=(prefix or "")+name+".rel.")

			if self.multiple:
				dbFilter.setFilterHook( lambda s, filter, value: self.filterHook( name, s, filter, value))
				dbFilter.setOrderHook( lambda s, orderings: self.orderHook( name, s, orderings) )

		elif name in rawFilter and rawFilter[ name ].lower() == "none":
			dbFilter = dbFilter.filter("%s =" % name, None)

		return dbFilter

	def buildDBSort( self, name, skel, dbFilter, rawFilter ):
		origFilter = dbFilter.datastoreQuery
		if origFilter is None or not "orderby" in rawFilter: #This query is unsatisfiable or not sorted
			return( dbFilter )
		if "orderby" in rawFilter and isinstance(rawFilter["orderby"], basestring) and rawFilter["orderby"].startswith( "%s." % name ):
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
			if _type=="rel" and (self.using is None or param not in self.using()):
				logging.warning( "Invalid filtering! %s is not a bone in 'using' of %s" % (param,name) )
				raise RuntimeError()
			if "orderdir" in rawFilter  and rawFilter["orderdir"]=="1":
				order = ( "%s.%s" % (_type,param), db.DESCENDING )
			else:
				order = ( "%s.%s" % (_type,param), db.ASCENDING )
			dbFilter = dbFilter.order( order )
			dbFilter.setFilterHook( lambda s, filter, value: self.filterHook( name, s, filter, value))
			dbFilter.setOrderHook( lambda s, orderings: self.orderHook( name, s, orderings))
		return( dbFilter )

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
			if refKey not in self.refKeys:
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
			if srcKey not in self.parentKeys:
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
				if k not in self.refKeys:
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
					if orderKey not in self.parentKeys:
						logging.warning( "Invalid ordering! %s is not in parentKeys of RelationalBone %s!" % (orderKey,name) )
						raise RuntimeError()
					if isinstance( order, tuple ):
						res.append( ("src.%s" % orderKey, order[1] ) )
					else:
						res.append( "src.%s" % orderKey )
		return( res )

	def refresh(self, valuesCache, boneName, skel):
		"""
			Refresh all values we might have cached from other entities.
		"""
		def updateInplace(relDict):
			"""
				Fetches the entity referenced by valDict["dest.key"] and updates all dest.* keys
				accordingly
			"""
			if isinstance(relDict, dict) and "dest" in relDict:
				valDict = relDict["dest"]
			else:
				logging.error("Invalid dictionary in updateInplace: %s" % relDict)
				return

			if "key" in valDict and valDict["key"]:
				originalKey = valDict["key"]
			else:
				logging.error("Invalid dictionary in updateInplace: %s" % valDict)
				return

			entityKey = normalizeKey(originalKey)
			if originalKey != entityKey:
				logging.info("Rewriting %s to %s" % (originalKey, entityKey))
				valDict["key"] = entityKey

			# Try to update referenced values;
			# If the entity does not exist with this key, ignore
			# (key was overidden above to have a new appid when transferred).
			newValues = None

			try:
				newValues = db.Get(entityKey)
				assert newValues is not None
			except db.EntityNotFoundError:
				#This entity has been deleted
				logging.info("The key %s does not exist" % entityKey)
			except:
				raise

			if newValues:
				for key in self._refSkelCache.keys():
					if key == "key":
						continue
					elif key in newValues:
						getattr(self._refSkelCache, key).unserialize(valDict, key, newValues)


		if not valuesCache[boneName]:
			return

		logging.info("Refreshing relationalBone %s of %s" % (boneName, skel.kindName))

		if isinstance(valuesCache[boneName], dict):
			updateInplace(valuesCache[boneName])

		elif isinstance(valuesCache[boneName], list):
			for k in valuesCache[boneName]:
				updateInplace(k)

	def getSearchTags(self, values, key):
		def getValues(res, skel, valuesCache):
			for k, bone in skel.items():
				if bone.searchable:
					for tag in bone.getSearchTags(valuesCache, k):
						if tag not in res:
							res.append(tag)
			return res
		value = values.get(key)
		res = []
		if not value:
			return
		if self.multiple:
			for val in value:
				if val["dest"]:
					res = getValues(res, self._refSkelCache, val["dest"])
				if val["rel"]:
					res = getValues(res, self._usingSkelCache, val["rel"])
		else:
			if value["dest"]:
				res = getValues(res, self._refSkelCache, value["dest"])
			if value["rel"]:
				res = getValues(res, self._usingSkelCache, value["rel"])
		return res

	def getSearchDocumentFields(self, valuesCache, name, prefix=""):
		"""
		Generate fields for Google Search API
		"""
		def getValues(res, skel, valuesCache, searchPrefix):
			for key, bone in skel.items():
				if bone.searchable:
					res.extend(bone.getSearchDocumentFields(valuesCache, key, prefix=searchPrefix))

		value = valuesCache.get(name)
		res = []

		if not value:
			return res

		if self.multiple:
			for idx, val in enumerate(value):
				searchPrefix = "%s%s_%s" % (prefix, name, str(idx))
				if val["dest"]:
					getValues(res, self._refSkelCache, val["dest"], searchPrefix)
				if val["rel"]:
					getValues(res, self._usingSkelCache, val["rel"], searchPrefix)
		else:
			searchPrefix = "%s%s" % (prefix, name)
			if value["dest"]:
				getValues(res, self._refSkelCache, value["dest"], searchPrefix)
			if value["rel"]:
				getValues(res, self._usingSkelCache, value["rel"], searchPrefix)

		return res


	def setBoneValue(self, valuesCache, boneName, value, append, *args, **kwargs):
		"""
			Set our value to 'value'.
			Santy-Checks are performed; if the value is invalid, we flip our value back to its original
			(default) value and return false.

			:param valuesCache: Dictionary with the current values from the skeleton we belong to
			:type valuesCache: dict
			:param boneName: The Bone which should be modified
			:type boneName: str
			:param value: The value that should be assigned. It's type depends on the type of that bone
			:type boneName: object
			:param append: If true, the given value is appended to the values of that bone instead of
				replacing it. Only supported on bones with multiple=True
			:type append: bool
			:return: Wherever that operation succeeded or not.
			:rtype: bool
		"""
		from server.skeleton import RefSkel, skeletonByKind
		def relSkelFromKey(key):
			if not isinstance(key, db.Key):
				key = db.Key(encoded=key)
			if not key.kind() == self.kind:
				logging.error("I got a key, which kind doesn't match my type! (Got: %s, my type %s)" % (key.kind(), self.kind))
				return None
			entity = db.Get(key)
			if not entity:
				logging.error("Key %s not found" % str(key))
				return None
			relSkel = RefSkel.fromSkel(skeletonByKind(self.kind), *self.refKeys)
			relSkel.unserialize(entity)
			return relSkel
		if append and not self.multiple:
			raise ValueError("Bone %s is not multiple, cannot append!" % boneName)
		if not self.multiple and not self.using:
			if not (isinstance(value, basestring) or isinstance(value, db.Key)):
				raise ValueError("You must supply exactly one Database-Key to %s" % boneName)
			realValue = (value, None)
		elif not self.multiple and self.using:
			if not isinstance(value, tuple) or len(value) != 2 or \
				not (isinstance(value[0], basestring) or isinstance(value[0], db.Key)) or \
				not isinstance(value[1], self.using):
					raise ValueError("You must supply a tuple of (Database-Key, relSkel) to %s" % boneName)
			realValue = value
		elif self.multiple and not self.using:
			if not (isinstance(value, basestring) or isinstance(value, db.Key)) and not (isinstance(value, list)) \
				and all([isinstance(x, basestring) or isinstance(x, db.Key) for x in value]):
					raise ValueError("You must supply a Database-Key or a list hereof to %s" % boneName)
			if isinstance(value, list):
				realValue = [(x, None) for x in value]
			else:
				realValue = [(value, None)]
		else:  # which means (self.multiple and self.using)
			if not (isinstance(value, tuple) and len(value) == 2 and \
				        (isinstance(value[0], basestring) or isinstance(value[0], db.Key)) \
					and isinstance(value[1], self.using)) and not (isinstance(value, list) and
					all((isinstance(x, tuple) and len(x)==2 and \
					(isinstance(x[0], basestring) or isinstance(x[0], db.Key)) \
					and isinstance(x[1], self.using) for x in value))):
						raise ValueError("You must supply (db.Key, RelSkel) or a list hereof to %s" % boneName)
			if not isinstance(value, list):
				realValue = [value]
			else:
				realValue = value
		if not self.multiple:
			relSkel = relSkelFromKey(realValue[0])
			if not relSkel:
				return False
			valuesCache[boneName] = {"dest": relSkel.getValuesCache(), "rel": realValue[1].getValuesCache() if realValue[1] else None}
		else:
			tmpRes = []
			for val in realValue:
				relSkel = relSkelFromKey(val[0])
				if not relSkel:
					return False
				tmpRes.append({"dest": relSkel.getValuesCache(), "rel": val[1].getValuesCache() if val[1] else None})
			if append:
				if not isinstance(valuesCache[boneName], list):
					valuesCache[boneName] = []
				valuesCache[boneName].extend(tmpRes)
			else:
				valuesCache[boneName] = tmpRes
		return True

	def getReferencedBlobs( self, valuesCache, name ):
		"""
			Returns the list of blob keys referenced from this bone
		"""
		def blobsFromSkel(skel, valuesCache):
			blobList = set()
			for key, _bone in skel.items():
				blobList.update(_bone.getReferencedBlobs(valuesCache, key))
			return blobList
		res = set()
		if name in valuesCache:
			if isinstance(valuesCache[name], list):
				for myDict in valuesCache[name]:
					if myDict["dest"]:
						res.update(blobsFromSkel(self._refSkelCache, myDict["dest"]))
					if myDict["rel"]:
						res.update(blobsFromSkel(self._usingSkelCache, myDict["rel"]))
			elif isinstance(valuesCache[name], dict):
				if valuesCache[name]["dest"]:
					res.update(blobsFromSkel(self._refSkelCache, valuesCache[name]["dest"]))
				if valuesCache[name]["rel"]:
					res.update(blobsFromSkel(self._usingSkelCache, valuesCache[name]["rel"]))
		return res
