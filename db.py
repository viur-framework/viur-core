# -*- coding: utf-8 -*-
from google.appengine.api import datastore, datastore_types, datastore_errors
from google.appengine.datastore import datastore_query, datastore_rpc
from google.appengine.api import memcache
from google.appengine.api import search
from server.config import conf
import logging

"""
	Tiny wrapper around google.appengine.api.datastore*.
	This just ensures that operations issued directly through the database-api
	dosn't interfere with our caching. If you need skeletons anyway, query the database
	using skel.all(); its faster and is able to serve more requests from cache.
"""
__cacheLockTime__ = 42 #Prevent an entity from creeping into the cache for 42 Secs if it just has been altered.
__cacheTime__ = 15*60 #15 Mins
__CacheKeyPrefix__ ="viur-db-cache:" #Our Memcache-Namespace. Dont use that for other purposes

def PutAsync( entities, **kwargs ):
	"""
		Asynchronously store one or more entities in the datastore.

		Identical to db.Put() except returns an asynchronous object. Call
		get_result() on the return value to block on the call and get the results.
	"""
	if isinstance( entities, Entity ):
		entities._fixUnindexedProperties()
	elif isinstance( entities, List ):
		for entity in entities:
			assert isinstance( entity, Entity )
			entity._fixUnindexedProperties()
	if conf["viur.db.caching" ]>0:
		if isinstance( entities, Entity ): #Just one:
			if entities.is_saved(): #Its an update
				memcache.delete( str( entities.key() ), namespace=__CacheKeyPrefix__, seconds=__cacheLockTime__  )
		elif isinstance( entities, list ):
			for entity in entities:
				assert isinstance( entity, Entity )
				if entity.is_saved(): #Its an update
					memcache.delete( str( entity.key() ), namespace=__CacheKeyPrefix__, seconds=__cacheLockTime__  )
	return( datastore.PutAsync( entities, **kwargs ) )

def Put( entities, **kwargs ):
	"""
		Store one or more entities in the datastore.

		The entities may be new or previously existing. For new entities, Put() will
		fill in the app id and key assigned by the datastore.

		If the argument is a single Entity, a single Key will be returned. If the
		argument is a list of Entity, a list of Keys will be returned.

		Args:
			entities: Entity or list of Entities
			config: Optional Configuration to use for this request, must be specified
			as a keyword argument.

		Returns:
			Key or list of Keys

		Raises:
			TransactionFailedError, if the Put could not be committed.
	"""
	if isinstance( entities, Entity ):
		entities._fixUnindexedProperties()
	elif isinstance( entities, list ):
		for entity in entities:
			assert isinstance( entity, Entity )
			entity._fixUnindexedProperties()
	if conf["viur.db.caching" ]>0:
		if isinstance( entities, Entity ): #Just one:
			if entities.is_saved(): #Its an update
				memcache.delete( str( entities.key() ), namespace=__CacheKeyPrefix__, seconds=__cacheLockTime__  )
		elif isinstance( entities, list ):
			for entity in entities:
				assert isinstance( entity, Entity )
				if entity.is_saved(): #Its an update
					memcache.delete( str( entity.key() ), namespace=__CacheKeyPrefix__, seconds=__cacheLockTime__  )
	return( datastore.Put( entities, **kwargs ) )
	
def GetAsync( keys, **kwargs ):
	"""
		Asynchronously retrieves one or more entities from the datastore.
		
		Identical to datastore.Get() except returns an asynchronous object. Call
		get_result() on the return value to block on the call and get the results.
	"""
	class AsyncResultWrapper:
		"""
			Wraps an result thats allready there into something looking
			like an RPC-Object.
		"""
		def __init__( self, res ):
			self.res = res
		
		def get_result( self ):
			return( self.res )
	if conf["viur.db.caching" ]>0 and not datastore.IsInTransaction():
		if isinstance( keys, datastore_types.Key ) or isinstance( keys, basestring ): #Just one:
			res = memcache.get( str(keys), namespace=__CacheKeyPrefix__ )
			if res:
				return( AsyncResultWrapper( res ) )
	#Either the result wasnt found, or we got a list of keys to fetch;
	# --> no caching possible
	return( datastore.GetAsync( keys, **kwargs ) )
	
def Get( keys, **kwargs ):
	"""
		Retrieves one or more entities from the datastore.

		Retrieves the entity or entities with the given key(s) from the datastore
		and returns them as fully populated Entity objects, as defined below. If
		there is an error, raises a subclass of datastore_errors.Error.

		If keys is a single key or string, an Entity will be returned, or
		EntityNotFoundError will be raised if no existing entity matches the key.

		However, if keys is a list or tuple, a list of entities will be returned
		that corresponds to the sequence of keys. It will include entities for keys
		that were found and None placeholders for keys that were not found.

		Args:
			keys: Key or string or list of Keys or strings
			config: Optional Configuration to use for this request, must be specified
			as a keyword argument.

		Returns:
			Entity or list of Entity objects
	"""
	if conf["viur.db.caching" ]>0  and not datastore.IsInTransaction():
		if isinstance( keys, datastore_types.Key ) or isinstance( keys, basestring ): #Just one:
			res = memcache.get( str(keys), namespace=__CacheKeyPrefix__ )
			if not res: #Not cached - fetch and cache it :)
				res = Entity.FromDatastoreEntity( datastore.Get( keys, **kwargs ) )
				res[ "id" ] = str( res.key() )
				memcache.set( str(res.key() ), res, time=__cacheTime__, namespace=__CacheKeyPrefix__ )
			return( res )
		#Either the result wasnt found, or we got a list of keys to fetch;
		elif isinstance( keys,list ):
			#Check Memcache first
			cacheRes = {}
			tmpRes = []
			keyList = [ str(x) for x in keys ]
			while keyList: #Fetch in Batches of 30 entries, as the max size for bulk_get is limited to 32MB
				currentBatch = keyList[ : 30]
				keyList = keyList[ 30: ]
				cacheRes.update( memcache.get_multi( currentBatch, namespace=__CacheKeyPrefix__) )
			#Fetch the rest from DB
			missigKeys = [ x for x in keys if not str(x) in cacheRes.keys() ]
			dbRes = [ Entity.FromDatastoreEntity(x) for x in datastore.Get( missigKeys ) if x is not None ]
			#Cache what we had fetched
			cacheMap = {}
			for res in dbRes:
				cacheMap[ str(res.key() ) ] = res
				if len( str( cacheMap ) ) > 800000:
					#Were approaching the 1MB limit
					try:
						memcache.set_multi( cacheMap, time=__cacheTime__ , namespace=__CacheKeyPrefix__ )
					except:
						pass
					cacheMap = {}
			if cacheMap:
				# Cache the remaining entries
				try:
					memcache.set_multi( cacheMap, time=__cacheTime__ , namespace=__CacheKeyPrefix__ )
				except:
					pass
			for key in [ str(x) for x in keys ]:
				if key in cacheRes.keys():
					tmpRes.append( cacheRes[ key ] )
				else:
					for e in dbRes:
						if str( e.key() ) == key:
							tmpRes.append ( e )
							break
			if conf["viur.debug.traceQueries"]:
				logging.debug( "Fetched a result-set from Datastore: %s total, %s from cache, %s from datastore" % (len(tmpRes),len( cacheRes.keys()), len( dbRes ) ) )
			return( tmpRes )
	if isinstance( keys, list ):
		return( [ Entity.FromDatastoreEntity(x) for x in datastore.Get( keys, **kwargs ) ] )
	else:
		return( Entity.FromDatastoreEntity( datastore.Get( keys, **kwargs ) ) )

def DeleteAsync(keys, **kwargs):
	"""
		Asynchronously deletes one or more entities from the datastore.

		Identical to datastore.Delete() except returns an asynchronous object. Call
		get_result() on the return value to block on the call.
	"""
	if conf["viur.db.caching" ]>0:
		if isinstance( keys, datastore_types.Key ): #Just one:
			memcache.delete( str( keys ), namespace=__CacheKeyPrefix__, seconds=__cacheLockTime__  )
		elif isinstance( keys, list ):
			for key in keys:
				assert isinstance( key, datastore_types.Key ) or isinstance( key, basestring )
				memcache.delete( str( key ), namespace=__CacheKeyPrefix__, seconds=__cacheLockTime__  )
	return( datastore.DeleteAsync( keys, **kwargs ) )
	
def Delete(keys, **kwargs):
	"""
		Deletes one or more entities from the datastore. Use with care!

		Deletes the given entity(ies) from the datastore. You can only delete
		entities from your app. If there is an error, raises a subclass of
		datastore_errors.Error.

		Args:
			# the primary key(s) of the entity(ies) to delete
			keys: Key or string or list of Keys or strings
			config: Optional Configuration to use for this request, must be specified
			as a keyword argument.

		Raises:
			TransactionFailedError, if the Delete could not be committed.
	"""
	if conf["viur.db.caching" ]>0:
		if isinstance( keys, datastore_types.Key ) or isinstance( keys, basestring ): #Just one:
			memcache.delete( str( keys ), namespace=__CacheKeyPrefix__, seconds=__cacheLockTime__  )
		elif isinstance( keys, list ):
			for key in keys:
				assert isinstance( key, datastore_types.Key ) or isinstance( key, basestring )
				memcache.delete( str( key ), namespace=__CacheKeyPrefix__, seconds=__cacheLockTime__  )
	return( datastore.Delete( keys, **kwargs ) )

def GetOrInsert( key, kindName=None, parent=None, **kwargs ):
	"""
		Either creates a new entity with the given key, or returns the existing one.
		Its guranteed that there is no race-condition here; it will never overwrite an
		previously created entity. Extra keyword arguments passed to this function will be
		used to populate the entity if it has to be created; otherwise they are ignored.
		
		@param key: The key which will be fetched/created. If key is a string, it will be used as the name for
			the new entity, therefor the collectionName is required in this case.
		@type key: db.Key or String
		@param kindName: Kind to use for that entity. Ignored if key is a db.Key
		@type kindName: String
		@param parent: The parent entity of our entity.
		@type parent: db.Key or None
	"""

	def txn( key, kwargs ):
		try:
			res = datastore.Get( key )
		except datastore_errors.EntityNotFoundError:
			res = Entity( kind=key.kind(), parent=key.parent(), name=key.name(), id=key.id() )
			for k, v in kwargs.items():
				res[ k ] = v
			datastore.Put( res )
		return( res )

	if not isinstance( key, datastore_types.Key ):
		try:
			key = datastore_types.Key( encoded=key )
		except:
			assert kindName
			key = datastore_types.Key.from_path( kindName, key, parent=parent )
	if datastore.IsInTransaction():
		return( txn(key, kwargs) )
	else:
		return( datastore.RunInTransaction( txn, key, kwargs ) )
	
class Query( object ):
	"""
		Thin wrapper around datastore.Query to provide a consistent
		(camelCase) API.
	"""
	
	def __init__(self, kind, srcSkelClass=None, *args, **kwargs ):
		super( Query, self ).__init__( )
		self.datastoreQuery = datastore.Query( kind, *args, **kwargs )
		self.srcSkel = srcSkelClass
		self.amount = 30
		self._filterHook = None
		self._orderHook = None
		self._origCursor = None
		self.origKind = kind

	def setFilterHook(self, hook):
		"""
			Installs callable "hook" as a callback function.
			"Hook" will be called each time a new filter constrain is added
			to the query. This allows f.e. the relationalBone to rewrite constrains added
			after the initial processing of the query has been done (ie by listFilter() methods)
		@param hook: The function to register as callback. None removes the currently active hook.
		@type hook: callable
		@return: The old registered hook (if any)
		"""
		old = self._filterHook
		self._filterHook = hook
		return( old )


	def setOrderHook(self, hook):
		"""
			Installs callable "hook" as a callback function.
			"Hook" will be called each time order() is called on that query.
			This allows f.e. the relationalBone to rewrite constrains added
			after the initial processing of the query has been done (ie by listFilter() methods)
		@param hook: The function to register as callback. None removes the currently active hook.
		@type hook: callable
		@return: The old registered hook (if any)
		"""
		old = self._orderHook
		self._orderHook = hook
		return( old )

	def mergeExternalFilter(self, filters ):
		"""
			Safely processes filters according to the datamodel.
			Its only valid to call this if the query has been created using skel.all().
			Its safe to pass filters recieved from an external source (a user);
			unknown/invalid filters will be ignored, so the query-object stayes in a 
			valid state even after processing malformed data.
			
			If you need complex queries (ie filter by relations), youll also need to use
			this function; the normal filter() cannot provide that.
		"""
		from server.bones import baseBone, relationalBone
		if self.srcSkel is None:
			raise NotImplementedError("This query has not been created using skel.all()")
		if self.datastoreQuery is None: #This query is allready unsatifiable and adding more constrains to this wont change this
			return( self )
		skel = self.srcSkel.clone()
		if skel.searchIndex and "search" in filters.keys(): #We perform a Search via Google API - all other parameters are ignored
			searchRes = search.Index( name=skel.searchIndex ).search( query=search.Query( query_string=filters["search"], options=search.QueryOptions( limit=25 ) ) )
			tmpRes = [ datastore_types.Key( encoded=x.doc_id[ 2: ] ) for x in searchRes ]
			if tmpRes:
				filters = []
				for x in tmpRes:
					filters.append( datastore.Query( self.getKind(), { "%s =" % datastore_types.KEY_SPECIAL_PROPERTY: x } ) )
				self.datastoreQuery = datastore.MultiQuery( filters, () )
			else:
				self.datastoreQuery = None
			return( self )
		#bones = [ (getattr( skel, key ), key) for key in dir( skel ) if not "__" in key and isinstance( getattr( skel, key ) , baseBone ) ]
		bones = [ (y,x) for x,y in skel.items() ]
		try:
			#First, filter non-relational bones
			for bone, key in [ x for x in bones if not isinstance( x[0], relationalBone ) ]:
				bone.buildDBFilter( key, skel, self, filters )
			#Second, process orderings of non-relational bones
			for bone, key in [ x for x in bones if not isinstance( x[0], relationalBone ) ]:
				bone.buildDBSort( key, skel, self, filters )
			#Now filter relational bones
			for bone, key in [ x for x in bones if isinstance( x[0], relationalBone ) ]:
				bone.buildDBFilter( key, skel, self, filters )
			#finally process orderings of nelational bones
			for bone, key in [ x for x in bones if isinstance( x[0], relationalBone ) ]:
				bone.buildDBSort( key, skel, self, filters )
		except RuntimeError:
			self.datastoreQuery = None
			return( self )
		if "search" in filters.keys():
			if isinstance( filters["search"], list ):
				taglist = [ "".join([y for y in unicode(x).lower() if y in conf["viur.searchValidChars"] ] ) for x in filters["search"] ]
			else:
				taglist = [ "".join([y for y in unicode(x).lower() if y in conf["viur.searchValidChars"] ]) for x in unicode(filters["search"]).split(" ")] 
			assert not isinstance( self.datastoreQuery, datastore.MultiQuery )
			origFilter = self.datastoreQuery
			queries = []
			for tag in taglist:
				q = datastore.Query( kind=origFilter.__kind )
				q[ "viur_tags" ] = tag
				queries.append( q )
			self.datastoreQuery = datastore.MultiQuery( queries, origFilter.__orderings )
			for k, v in origFilter.items():
				self.datastoreQuery[ k ] = v
		if "cursor" in filters.keys() and filters["cursor"] and filters["cursor"].lower()!="none":
			self.cursor( filters["cursor"] )
		if "amount" in list(filters.keys()) and str(filters["amount"]).isdigit() and int( filters["amount"] ) >0 and int( filters["amount"] ) <= 99:
			self.limit( int(filters["amount"]) )
		if "postProcessSearchFilter" in dir( skel ):
			skel.postProcessSearchFilter( self, filters )
		return( self )
	
	def filter(self, filter, value=None ):
		"""
			Adds contrains to this query.
			The following examples are equivalent:
				filter( "name", "John" )
				filter( {"name": "John"} )

			@param filter: A dictionary to read the filters from, or a string (name of that filter)
			@type filter: Dict or String
			@param value: The value of that filter. Only valid, if key is a string.
			@type value: Int, Long, Float, Bytes, String, List or DateTime
		"""
		if self.datastoreQuery is None:
			#This query is already unsatisfiable and adding more constrains to this won't change this
			return( self )
		if isinstance( filter, dict ):
			for k, v in filter.items():
				self.filter( k, v )
			return( self )
		if self._filterHook is not None:
			try:
				r = self._filterHook( self, filter, value )
			except RuntimeError:
				self.datastoreQuery = None
				return( self )
			if r is None:
				return( self )
			filter, value = r
		if value!=None and (filter.endswith(" !=") or filter.lower().endswith(" in")):
			if isinstance( self.datastoreQuery, datastore.MultiQuery ):
				raise NotImplementedError("You cannot use multiple IN or != filter")
			origQuery = self.datastoreQuery
			queries = []
			if filter.endswith("!="):
				q = datastore.Query( kind=self.getKind() )
				q[ "%s <" % filter.split(" ")[0] ] = value
				queries.append( q )
				q = datastore.Query( kind=self.getKind() )
				q[ "%s >" % filter.split(" ")[0] ] = value
				queries.append( q )
			else: #IN filter
				if not (isinstance( value, list ) or isinstance( value, tuple ) ):
					raise NotImplementedError("Value must be list or tuple if using IN filter!")
				for val in value:
					q = datastore.Query( kind=self.getKind() )
					q[ "%s =" % filter.split(" ")[0] ] = val
					queries.append( q )
			self.datastoreQuery = MultiQuery( queries, origQuery.__orderings )
			for k,v in origQuery.items():
				self.datastoreQuery[ k ] = v
		elif filter and value!=None:
			self.datastoreQuery[ filter ] = value
		else:
			raise NotImplementedError("Incorrect call to query.filter()!")
		return( self )
	
	def order(self, *orderings):
		"""
			Specify how the query results should be sorted.

			Result entities will be sorted by the first property argument, then by the
			second, and so on. For example, this:

			> query = Query('Person')
			> query.Order('bday', ('age', Query.DESCENDING))

			sorts everyone in order of their birthday, starting with January 1.
			People with the same birthday are sorted by age, oldest to youngest.

			The direction for each sort property may be provided; if omitted, it
			defaults to ascending.

			Order() may be called multiple times. Each call resets the sort order
			from scratch.

			If an inequality filter exists in this Query it must be the first property
			passed to Order. Any number of sort orders may be used after the
			inequality filter property. Without inequality filters, any number of
			filters with different orders may be specified.

			Entities with multiple values for an order property are sorted by their
			lowest value.

			Note that a sort order implies an existence filter! In other words,
			Entities without the sort order property are filtered out, and *not*
			included in the query results.

			If the sort order property has different types in different entities - ie,
			if bob['id'] is an int and fred['id'] is a string - the entities will be
			grouped first by the property type, then sorted within type. No attempt is
			made to compare property values across types.

			Raises BadArgumentError if any argument is of the wrong format.

			Args:
			      # the properties to sort by, in sort order. each argument may be either a
			      # string or (string, direction) 2-tuple.

			Returns:
				# this query
		"""
		if self._orderHook is not None:
			try:
				orderings = self._orderHook( self, orderings )
			except RuntimeError:
				self.datastoreQuery = None
				return( self )
			if orderings is None:
				return( self )
		if self.datastoreQuery is None:
			return
		self.datastoreQuery.Order( *orderings )
		return( self )

	def ancestor(self, ancestor):
		"""
			Sets an ancestor for this query.

			This restricts the query to only return result entities that are descended
			from a given entity. In other words, all of the results will have the
			ancestor as their parent, or parent's parent, or etc.

			Raises BadArgumentError or BadKeyError if parent is not an existing Entity
			or Key in the datastore.

			Args:
				# the key must be complete
				ancestor: Entity or Key

			Returns:
				# this query
			Query
		"""
		self.datastoreQuery.Ancestor( ancestor )
		return( self )
	
	def cursor( self, cursor ):
		"""
			Sets the start cursor for this query.
			The result set will only include results after that cursor.
			The cursor must be generated by an earlier query with exactly the same parameters.
			Its safe to use client-supplied cursors, a cursor can't be abused to access entities which don't
			match the current filters.
		"""
		if isinstance( cursor, basestring ):
			cursor = datastore_query.Cursor( urlsafe=cursor )
		elif isinstance( cursor, datastore_query.Cursor ) or cursor==None:
			pass
		else:
			raise ValueError("Cursor must be String, datastore_query.Cursor or None")
		qo = self.datastoreQuery.__query_options
		self.datastoreQuery.__query_options = datastore_query.QueryOptions(	keys_only=qo.keys_only, 
											produce_cursors=qo.produce_cursors,
											start_cursor=cursor,
											end_cursor=qo.end_cursor,
											projection=qo.projection )
		self._origCursor = cursor
		return( self )
	
	def limit( self, amount ):
		"""
			Limit this query to return at most #amount results.
			Set to 0 to disable (use with care!).
		"""
		self.amount = amount
	
	def isKeysOnly(self):
		"""
			Returns True if this query is keys only, false otherwise.
		"""
		return( self.datastoreQuery.IsKeysOnly() )

	def getQueryOptions(self):
		"""
			Returns a datastore_query.QueryOptions for the current instance.
		"""
		return( self.datastoreQuery.GetQueryOptions() )

	def getQuery(self):
		"""
			Returns a datastore_query.Query for the current instance.
		"""
		return( self.datastoreQuery.GetQuery() )

	def getOrder(self):
		"""
			Gets a datastore_query.Order for the current instance.

			Returns:
				datastore_query.Order or None if there are no sort orders set on the
				current Query.
		"""
		if self.datastoreQuery is None:
			return( None )
		else:
			return( self.datastoreQuery.GetOrder() )
	
	def getFilter(self):
		"""
			Returns the filters applied to the current query as dictionary.
		"""
		if self.datastoreQuery is None:
			return( None )
		return( { k:v for (k, v) in self.datastoreQuery.items() } )
	
	def getOrders(self):
		"""
			Returns a list of orders applied to this query.
			Each element in the list returned (if any),
			is a tuple (property,direction).
			Property is the name of the property used to sort,
			direction a Bool (false => ascending, True => descending )
		"""
		try:
			order = self.datastoreQuery.__orderings
			return( [ (prop, dir) for (prop, dir) in order ] )
		except:
			return( [] )

	def getCursor(self):
		"""
			Get the cursor from the last run of this query.

			The source of this cursor varies depending on what the last call was:
			- Run: A cursor that points immediately after the last result pulled off
			  the returned iterator.
			- Get: A cursor that points immediately after the last result in the
			  returned list.
			- Count: A cursor that points immediately after the last result counted.

			Returns:
				A datastore_query.Cursor object that can be used in subsequent query
				requests.

			Raises:
				AssertionError: The query has not yet been run or cannot be compiled.
		"""
		if self.datastoreQuery is None:
			return( None )
		else:
			return( self.datastoreQuery.GetCursor() )

	def getKind(self):
		"""
			Returns the kind of our query.
			@returns String
		"""
		return( self.datastoreQuery.__kind )
	
	def setKind( self, newKind ):
		"""
			Changes the kind of our query.
		"""
		if self.datastoreQuery is None:
			return
		self.datastoreQuery.__kind = newKind
		
	def getAncestor(self):
		"""
			Returns the ancestor of this query (if any)
			@returns String or None
		"""
		return( self.datastoreQuery.ancestor )

	def run(self, limit=-1, keysOnly=False, **kwargs):
		"""
			Runs this query.

			If a filter string is invalid, raises BadFilterError. If a filter value is
			invalid, raises BadValueError. If an IN filter is provided, and a sort
			order on another property is provided, raises BadQueryError.

			If you know in advance how many results you want, use limit=#. It's
			more efficient.

			Args:
				kwargs: Any keyword arguments accepted by datastore_query.QueryOptions().

			Returns:
				# an iterator that provides access to the query results
				Iterator
		"""
		if self.datastoreQuery is None:
			return( None )
		kwargs["limit"] = limit if limit!=-1 else self.amount
		if not isinstance( self.datastoreQuery, datastore.MultiQuery ):
			internalKeysOnly = True
		else:
			internalKeysOnly = False
		if conf["viur.db.caching" ]<2:
			# Query-Caching is disabled, make this query keys-only if (and only if) explicitly requested for this query
			internalKeysOnly = keysOnly
		res = list( self.datastoreQuery.Run( keys_only=internalKeysOnly, **kwargs ) )
		if conf["viur.debug.traceQueries"]:
			kindName = self.getKind()
			orders = self.getOrders()
			filters = self.getFilter()
			logging.debug("Queried %s with filter %s and orders %s. Returned %s results" % (kindName, filters, orders, len(res)))
		if keysOnly and not internalKeysOnly: #Wanted key-only, but this wasnt directly possible
			if len(res)>0 and res[0].key().kind()!=self.origKind and res[0].key().parent().kind()==self.origKind:
				#Fixing the kind - it has been changed (probably by quering an relation)
				res = [ x.key().parent() for x in res ]
			return( [x.key() for x in res] )
		elif keysOnly and internalKeysOnly: #Keys-only requested and we did it
			if len(res)>0 and res[0].kind()!=self.origKind and res[0].parent().kind()==self.origKind:
				#Fixing the kind - it has been changed (probably by quering an relation)
				res = [ x.parent() for x in res ]
			return( res )
		elif not keysOnly and not internalKeysOnly: #Full query requested and we did it
			if len(res)>0 and res[0].key().kind()!=self.origKind and res[0].key().parent().kind()==self.origKind:
				#Fixing the kind - it has been changed (probably by quering an relation)
				res = Get( [ x.key().parent() for x in res ] )
			return( res )
		else: #Well.. Full results requested, but we did keys-only
			if len(res)>0 and res[0].kind()!=self.origKind and res[0].parent().kind()==self.origKind:
				#Fixing the kind - it has been changed (probably by quering an relation)
				res = [ x.parent() for x in res ]
			return( Get( res ) )
	
	def fetch(self, limit=-1, **kwargs ):
		"""
			Like run, but returns a skeleton.Skellist instance instead
			of an result iterator. The query must be limited.
		"""
		if self.srcSkel is None:
			raise NotImplementedError("This query has not been created using skel.all()")
		amount = limit if limit!=-1 else self.amount
		if amount < 1 or amount > 100:
			raise NotImplementedError("This query is not limited! You must specify an upper bound using limit() between 1 and 100")
		from server.skeleton import SkelList
		res = SkelList( self.srcSkel )
		dbRes = self.run( amount )
		if dbRes is None:
			return( res )
		for e in dbRes:
			s = self.srcSkel.clone()
			s.setValues( e, key=e.key() )
			res.append( s )
		try:
			c = self.datastoreQuery.GetCursor()
			if c:
				res.cursor = c.urlsafe()
			else:
				res.cursor = None
		except AssertionError: #No Cursors avaiable on MultiQueries ( in or != )
			res.cursor = None
		return( res )
	
	def iter(self, keysOnly=False):
		"""
			Returns an iterator for the results.
			Advantage: Its possible to iterate over a large result-set,
			as it hasn't have to be pulled in advance from the datastore.
			Disadvantage: No Caching (yet)
			Note: This intentionally ignores the limit set by self.limt() -
			it yields *all* results.
			
			Warning: If iterating over a large result set, make sure the query
			supports cursors. Otherwise, it might not return all results as the
			appengine doesn't maintain the view for a query for more than ~30 seconds.
			
			@param keysOnly: Set to true if you just want the keys
			@type keysOnly: Bool
		"""
		if self.datastoreQuery is None: #Noting to pull here
			raise StopIteration()
		if isinstance( self.datastoreQuery, datastore.MultiQuery ) and keysOnly:
			# Wantet KeysOnly, but MultiQuery is unable to give us that.
			for res in self.datastoreQuery.Run():
				yield res.key()
		else: #The standard-case
			stopYield = False
			lastCursor = None
			while not stopYield:
				try:
					for res in self.datastoreQuery.Run( keys_only=keysOnly ): 
						yield res
						try:
							lastCursor = self.datastoreQuery.GetCursor()
						except Exception as e:
							pass
					stopYield = True # No more results to yield
				except:
					if lastCursor is None:
						stopYield = True
						logging.warning("Cannot this continue this query - it has no cursors")
						logging.warning("Not all results have been yielded!")
					else:
						logging.debug("Continuing iter() on fresh a query")
						q = self.clone()
						q.cursor( lastCursor )
						self.datastoreQuery = q.datastoreQuery
						lastCursor = None
	
	def get( self ):
		"""
			Returns the first entity of the current query or None if the result-set is empty.
			
			@returns: Dict or None if the result-set is empty
		"""
		try:
			res = list( self.run( limit=1 ) )[0]
			return( res )
		except IndexError: #Empty result-set
			return( None )
		except TypeError: #Also Empty result-set
			return( None )
	
	def getSkel( self ):
		"""
			Like get, but returns an skeleton.Skeleton instance.
			Its only valid to call this, if this query has been created using skel.all()
			
			@returns: skeleton.Skeleton or None if the result-set is empty
		"""
		if self.srcSkel is None:
			raise NotImplementedError("This query has not been created using skel.all()")
		res = self.get()
		if res is None:
			return( None )
		s = self.srcSkel.clone()
		s.setValues( res, key=res.key() )
		return( s )
	
	def count( self, limit=1000, **kwargs ):
		"""
			Returns the number of entities that this query matches.

			Args:
				limit, a number or None. If there are more results than this, stop short
				and just return this number. Providing this argument makes the count
				operation more efficient.
				config: Optional Configuration to use for this request.

			Returns:
				The number of results.
			"""
		return( self.datastoreQuery.Count( limit, **kwargs ) )
	
	def clone(self, keysOnly=None):
		"""
			Returns a deep copy of the current query
		"""
		if keysOnly is None:
			keysOnly = self.isKeysOnly()
		res = Query( self.getKind(), self.srcSkel, keys_only=keysOnly )
		res.limit( self.amount )
		for k, v in self.getFilter().items():
			res.filter( k, v )
		orders = self.getOrders()
		if len( orders )==1:
			res.order( orders[0] )
		elif len( orders ) > 1:
			res.order( tuple( orders ) )
		return( res )


class Entity( datastore.Entity ):
	"""
		Wraps datastore.Entity to prevent
		trying adding a string>500 chars
		to an index and providing a camelCase-API.
	"""
	def _fixUnindexedProperties( self ):
		"""
			Ensures that no property with strlen > 500 makes it into the index.
		"""
		unindexed = list( self.getUnindexedProperties() )
		for k,v in self.items():
			if isinstance( v, basestring ) and len( v )>=500 and not k in unindexed:
				logging.warning("Your property %s cant be indexed!" % k)
				unindexed.append( k )
			elif isinstance( v, list ) or isinstance( v, tuple() ):
				if any( [ isinstance(x,basestring) and len(x)>=500 for x in v] ) and not k in unindexed:
					logging.warning("Your property %s cant be indexed!" % k)
					unindexed.append( k )
		self.set_unindexed_properties( unindexed )

	def isSaved(self):
		"""
			Returns True if this entity has been saved to the datastore.
		"""
		return( self.is_saved() )
	
	def entityGroup(self):
		"""
			Returns this entity's entity group as a Key.

			Note that the returned Key will be incomplete if this is a a root entity
			and its key is incomplete.
		"""
		return( self.entity_group() )

	def getUnindexedProperties(self):
		"""
			Returns this entity's unindexed properties, as a frozenset of strings.
		"""
		return( self.unindexed_properties() )
	
	def setUnindexedProperties(self, unindexed_properties):
		"""
			Sets the list of unindexed properties.
			Properties listed here are *not* saved in an index;
			its impossible to use them in a query filter / sort.
			But you'll save one db-write op per property listed here.
		"""
		self.set_unindexed_properties( unindexed_properties )

	def __setitem__(self, name, value):
		"""
			Implements the [] operator. Used to set property value(s).

			If the property name is the empty string or not a string, raises
			BadPropertyError. If the value is not a supported type, raises
			BadValueError.
		"""
		if isinstance(value,list) or isinstance(value,tuple):
			# We cant store an empty list, so we catch any attempts
			# and store None. As "does not exists" queries aren't
			# possible anyway, this makes no difference
			if len( value ) == 0:
				value = None
		super( Entity, self ).__setitem__( name, value )
	
	def set( self, key, value, indexed=True ):
		"""
			Sets key to value.
		"""
		if not indexed:
			unindexed = list( self.getUnindexedProperties() )
			if not key in unindexed:
				self.setUnindexedProperties( unindexed+[key] )
		self[ key ] = value

	@staticmethod
	def FromDatastoreEntity( entity ):
		"""
			Converts a datastore.Entity into this class.
			Required, as datastore.Get always returns a
			datastore.Entity (and it seems that currently
			there is no valid way to change that).
		"""
		res = Entity(	entity.kind(), parent=entity.key().parent(), _app=entity.key().app(),
				name=entity.key().name(), id=entity.key().id(),
				unindexed_properties=entity.unindexed_properties(),
				namespace=entity.namespace() )
		res.update( entity )
		return( res )


AllocateIdsAsync = datastore.AllocateIdsAsync
AllocateIds = datastore.AllocateIds
RunInTransaction = datastore.RunInTransaction
RunInTransactionCustomRetries = datastore.RunInTransactionCustomRetries
RunInTransactionOptions = datastore.RunInTransactionOptions
TransactionOptions = datastore_rpc.TransactionOptions

Key = datastore_types.Key

## Errors ##
Error = datastore_errors.Error
BadValueError = datastore_errors.BadValueError
BadPropertyError = datastore_errors.BadPropertyError
BadRequestError = datastore_errors.BadRequestError
EntityNotFoundError = datastore_errors.EntityNotFoundError
BadArgumentError = datastore_errors.BadArgumentError
QueryNotFoundError = datastore_errors.QueryNotFoundError
TransactionNotFoundError = datastore_errors.TransactionNotFoundError
Rollback = datastore_errors.Rollback
TransactionFailedError = datastore_errors.TransactionFailedError
BadFilterError = datastore_errors.BadFilterError
BadQueryError = datastore_errors.BadQueryError
BadKeyError = datastore_errors.BadKeyError
InternalError = datastore_errors.InternalError
NeedIndexError = datastore_errors.NeedIndexError
ReferencePropertyResolveError = datastore_errors.ReferencePropertyResolveError
Timeout = datastore_errors.Timeout
CommittedButStillApplying = datastore_errors.CommittedButStillApplying

DatastoreQuery = datastore.Query
MultiQuery = datastore.MultiQuery
Cursor = datastore_query.Cursor

#Consts
KEY_SPECIAL_PROPERTY = datastore_types.KEY_SPECIAL_PROPERTY
ASCENDING = datastore_query.PropertyOrder.ASCENDING
DESCENDING = datastore_query.PropertyOrder.DESCENDING

__all__ = [	PutAsync, Put, GetAsync, Get, DeleteAsync, Delete, AllocateIdsAsync, AllocateIds, RunInTransaction, RunInTransactionCustomRetries, RunInTransactionOptions, TransactionOptions,
		Error, BadValueError, BadPropertyError, BadRequestError, EntityNotFoundError, BadArgumentError, QueryNotFoundError, TransactionNotFoundError, Rollback, 
		TransactionFailedError, BadFilterError, BadQueryError, BadKeyError, BadKeyError, InternalError, NeedIndexError, ReferencePropertyResolveError, Timeout,
		CommittedButStillApplying, Entity, Query, DatastoreQuery, MultiQuery, Cursor, KEY_SPECIAL_PROPERTY, ASCENDING, DESCENDING ]
