# -*- coding: utf-8 -*-
from server.bones import baseBone
from server.config import conf
import logging

class stringBone( baseBone ):
	type = "str"
	
	def __init__(self, caseSensitive = True, multiple=False, *args, **kwargs ):
		super( stringBone, self ).__init__( *args, **kwargs )
		self.caseSensitive = caseSensitive
		self.multiple = multiple

	def serialize( self, name ):
		if self.caseSensitive:
			return( super( stringBone, self ).serialize( name ) )
		else:
			if name == "id":
				return( { } )
			else:
				return( {	name: self.value, 
						name+"_idx": unicode( self.value ).lower() } )

	def fromClient( self, value ):
		if self.multiple:
			self.value = []
			if not value:
				return( "No value entered" )
			if not isinstance( value, list ):
				value = [value]
			for val in value:
				if not self.canUse( val ):
					if isinstance(val, str) or isinstance( val,  unicode ):
						self.value.append( val.strip().replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;")[0:254] )
					else: 
						self.value.append( unicode(val).strip().replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;")[0:254] )
			if( len( self.value ) > 0):
				self.value = self.value[0:254]
				return( None )
			else:
				return( "No valid value entered" )
		else:
			err = self.canUse( value )
			if not err:
				if not value:
					self.value = u""
					return( "No value entered" )
				self.value = value[0:500]
				return( None )
			else:
				return( err )

	def buildDBFilter( self, name, skel, dbFilter, rawFilter ):
		if not name in rawFilter.keys() and not any( [x.startswith(name+"$") for x in rawFilter.keys()] ):
			return( super( stringBone, self ).buildDBFilter( name, skel, dbFilter, rawFilter ) )
		if not self.searchable:
			logging.warning( "Invalid searchfilter! %s is not searchable!" % name )
			raise RuntimeError()
		hasInequalityFilter = False
		if name+"$lk" in rawFilter.keys(): #Do a prefix-match
			if not self.caseSensitive:
				dbFilter[ name +"_idx >=" ] = unicode( rawFilter[name+"$lk"] ).lower()
				dbFilter[ name +"_idx <" ] = unicode( rawFilter[name+"$lk"]+u"\ufffd" ).lower()
			else:
				dbFilter[ name + " >=" ] = unicode( rawFilter[name+"$lk"] )
				dbFilter[ name + " < " ] = unicode( rawFilter[name+"$lk"]+u"\ufffd" )
			hasInequalityFilter = True
		if name+"$gt" in rawFilter.keys(): #All entries after
			if not self.caseSensitive:
				dbFilter[ name +"_idx >" ] = unicode( rawFilter[name+"$gt"] ).lower()
			else:
				dbFilter[ name + " >"] =  unicode( rawFilter[name+"$gt"] )
			hasInequalityFilter = True
		if name+"$lt" in rawFilter.keys(): #All entries before
			if not self.caseSensitive:
				dbFilter[ name +"_idx <" ] = unicode( rawFilter[name+"$lt"] ).lower()
			else:
				dbFilter[ name + " <" ] =  unicode( rawFilter[name+"$lt"] )
			hasInequalityFilter = True
		if 0 and hasInequalityFilter:
			#Enforce a working sort-order
			if "orderdir" in rawFilter.keys()  and rawFilter["orderdir"]=="1":
				if not self.caseSensitive:
					dbFilter = dbFilter.order( -ndb.GenericProperty( name+"_idx" ) )
				else:
					dbFilter = dbFilter.order( -ndb.GenericProperty( name ) )
			else:
				if not self.caseSensitive:
					dbFilter = dbFilter.order( ndb.GenericProperty( name+"_idx" ) )
				else:
					dbFilter = dbFilter.order( ndb.GenericProperty( name ) )
		if name in rawFilter.keys(): #Normal, strict match
			if not self.caseSensitive:
				dbFilter[ name+"_idx" ] = unicode( rawFilter[name] ).lower()
			else:
				dbFilter[ name ]= unicode( rawFilter[name] )
		return( dbFilter )

	def buildDBSort( self, name, skel, dbFilter, rawFilter ):
		if "orderby" in list(rawFilter.keys()) and rawFilter["orderby"] == name:
			if not self.searchable:
				logging.warning( "Invalid ordering! %s is not searchable!" % name )
				raise RuntimeError()
			if self.caseSensitive:
				prop = name
			else:
				prop = name+"_idx"
			if "orderdir" in rawFilter.keys()  and rawFilter["orderdir"]=="1":
				order = ( prop, dbFilter.DESCENDING )
			else:
				order = ( prop, dbFilter.ASCENDING )
			logging.error("p1")
			inEqFilter = [ x for x in dbFilter.keys() if (">" in x[ -3: ] or "<" in x[ -3: ] or "!=" in x[ -4: ] ) ]
			if inEqFilter:
				logging.error("p2")
				inEqFilter = inEqFilter[ 0 ][ : inEqFilter[ 0 ].find(" ") ]
				if inEqFilter != order[0]:
					logging.error("p3")
					logging.warning("I fixed you query! Impossible ordering changed to %s, %s" % (inEqFilter, order[0]) )
					dbFilter.Order( inEqFilter, order )
				else:
					logging.error("p4")
					dbFilter.Order( order )
			else:
				logging.error("p5")
				logging.error( order )
				dbFilter.Order( order )
		return( dbFilter )

		
	def getTags(self):
		res = []
		if not self.value:
			return( res )
		value = self.value
		for line in unicode(value).splitlines():
			for key in line.split(" "):
				key = "".join( [ c for c in key if c.lower() in conf["viur.searchValidChars"] ] )
				if key and key not in res and len(key)>3:
					res.append( key.lower() )
		return( res )
