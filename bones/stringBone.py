# -*- coding: utf-8 -*-
from server.bones import baseBone
from server.config import conf
from server import db
from server.session import current as currentSession
import logging


class LanguageWrapper( dict ):
	"""
		Wrapper-class for a multi-language value.
		Its a dictionary, allowing accessing each stored language,
		but can also be used as a string, in which case it tries to
		guess the corrent language.
	"""
	
	def __init__( self, languages ):
		super( LanguageWrapper, self ).__init__()
		self.languages = languages
	
	def __str__( self ):
		lang = currentSession.getLanguage()
		if not lang:
			lang = self.languages[ 0 ]
		if lang in self.keys(): #The users language is avaiable :)
			return( self[ lang ] )
		else: #We need to select another lang for him
			for lang in self.languages:
				if lang in self.keys() and self[ lang ]:
					return( self[ lang ] )
		return( None )

class stringBone( baseBone ):
	type = "str"
	
	def __init__(self, caseSensitive = True, multiple=False, languages=None, *args, **kwargs ):
		super( stringBone, self ).__init__( *args, **kwargs )
		if not caseSensitive and not self.indexed:
			raise ValueError("Creating a case-insensitive index without actually writing the index is nonsense.")
		self.caseSensitive = caseSensitive
		if not (languages is None or (isinstance( languages, list ) and len(languages)>0 and all( [isinstance(x,basestring) for x in languages] ))):
			raise ValueError("languages must be None or a list of strings ")
		self.languages = languages
		self.multiple = multiple

	def serialize( self, name, entity ):
		for k in entity.keys(): #Remove any old data
			if k.startswith("%s." % name ):
				del entity[ k ]
		if not self.languages:
			if self.caseSensitive:
				return( super( stringBone, self ).serialize( name, entity ) )
			else:
				if name != "id":
					entity.set( name, self.value, self.indexed )
					entity.set( name+".idx", unicode( self.value ).lower(), self.indexed )
		else: #Write each language separately
			if not self.value:
				return( entity )
			if isinstance( self.value, basestring ) or (isinstance( self.value, list ) and self.multiple): #Convert from old format
				lang = self.languages[0]
				entity.set( "%s.%s" % (name, lang), self.value, self.indexed )
				if not self.caseSensitive:
					if isinstance( self.value, basestring ):
						entity.set( "%s.%s.idx" % (name, lang), self.value.lower(), self.indexed )
					else:
						entity.set( "%s.%s.idx" % (name, lang), [x.lower for x in self.value], self.indexed )
			else:
				assert isinstance( self.value, dict)
				for lang in self.languages:
					if lang in self.value.keys():
						val = self.value[ lang ]
						entity.set( "%s.%s" % (name, lang), self.value[lang], self.indexed )
						if not self.caseSensitive:
							if isinstance( val, basestring ):
								entity.set( "%s.%s.idx" % (name, lang), val.lower(), self.indexed )
							else:
								entity.set( "%s.%s.idx" % (name, lang), [x.lower for x in val], self.indexed )
		return( entity )
		
	def unserialize( self, name, expando ):
		"""
			Inverse of serialize. Evaluates whats
			read from the datastore and populates
			this bone accordingly.
			@param name: The property-name this bone has in its Skeleton (not the description!)
			@type name: String
			@param expando: An instance of the dictionary-like db.Entity class
			@type expando: db.Entity
		"""
		if not self.languages:
			if name in expando.keys():
				self.value = expando[ name ]
		else:
			self.value = LanguageWrapper( self.languages )
			for lang in self.languages:
				if "%s.%s" % ( name, lang ) in expando.keys():
					val = expando[ "%s.%s" % ( name, lang ) ]
					if isinstance( val, list ) and not self.multiple:
						val = ", ".join( val )
					self.value[ lang ] = val
			if not self.value.keys(): #Got nothing
				if name in expando.keys(): #Old (non-multi-lang) format
					self.value[ self.languages[0] ] = expando[ name ]
		return( True )

	def fromClient( self, name, data ):
		"""
			Reads a value from the client.
			If this value is valid for this bone,
			store this value and return None.
			Otherwise our previous value is
			left unchanged and an error-message
			is returned.
			
			@param name: Our name in the skeleton
			@type name: String
			@param data: *User-supplied* request-data
			@type data: Dict
			@returns: None or String
		"""
		def escapeValue( val ):
			return( unicode(val).strip().replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;")[0:254] )
		if name in data.keys():
			value = data[ name ]
		else:
			value = None
		if self.multiple and self.languages:
			self.value = LanguageWrapper( self.languages )
			for lang in self.languages:
				self.value[ lang ] = []
				if "%s.%s" % ( name, lang ) in data.keys():
					val = data["%s.%s" % ( name, lang )]
					if isinstance( val, basestring ):
						self.value[ lang ].append( escapeValue( val ) )
					elif isinstance( val, list ):
						for v in val:
							self.value[ lang ].append( escapeValue( v ) )
			if not any( self.value.values() ):
				return( "No value entered" )
			else:
				return( None )
		if self.multiple and not self.languages:
			self.value = []
			if not value:
				return( "No value entered" )
			if not isinstance( value, list ):
				value = [value]
			for val in value:
				if not self.canUse( val ):
					self.value.append( escapeValue( val ) )
			if( len( self.value ) > 0):
				self.value = self.value[0:254] #Max 254 Keys
				return( None )
			else:
				return( "No valid value entered" )
		elif not self.multiple and self.languages:
			self.value = LanguageWrapper( self.languages )
			for lang in self.languages:
				if "%s.%s" % ( name, lang ) in data.keys():
					self.value[ lang ] = escapeValue( data["%s.%s" % ( name, lang )] )
		else:
			err = self.canUse( value )
			if not err:
				if not value:
					self.value = u""
					return( "No value entered" )
				self.value = escapeValue( value )
				return( None )
			else:
				return( err )

	def buildDBFilter( self, name, skel, dbFilter, rawFilter ):
		if not name in rawFilter.keys() and not any( [x.startswith(name+"$") for x in rawFilter.keys()] ):
			return( super( stringBone, self ).buildDBFilter( name, skel, dbFilter, rawFilter ) )
		if not self.indexed:
			logging.warning( "Invalid searchfilter! %s is not indexed!" % name )
			raise RuntimeError()
		hasInequalityFilter = False
		if name+"$lk" in rawFilter.keys(): #Do a prefix-match
			if not self.caseSensitive:
				dbFilter.filter( name +"_idx >=", unicode( rawFilter[name+"$lk"] ).lower() )
				dbFilter.filter( name +"_idx <", unicode( rawFilter[name+"$lk"]+u"\ufffd" ).lower() )
			else:
				dbFilter.filter( name + " >=", unicode( rawFilter[name+"$lk"] ) )
				dbFilter.filter( name + " < ", unicode( rawFilter[name+"$lk"]+u"\ufffd" ) )
			hasInequalityFilter = True
		if name+"$gt" in rawFilter.keys(): #All entries after
			if not self.caseSensitive:
				dbFilter.filter( name +"_idx >", unicode( rawFilter[name+"$gt"] ).lower() )
			else:
				dbFilter.filter( name + " >", unicode( rawFilter[name+"$gt"] ) )
			hasInequalityFilter = True
		if name+"$lt" in rawFilter.keys(): #All entries before
			if not self.caseSensitive:
				dbFilter.filter( name +"_idx <", unicode( rawFilter[name+"$lt"] ).lower() )
			else:
				dbFilter.filter( name + " <", unicode( rawFilter[name+"$lt"] ) )
			hasInequalityFilter = True
		if name in rawFilter.keys(): #Normal, strict match
			if not self.caseSensitive:
				dbFilter.filter( name+"_idx", unicode( rawFilter[name] ).lower() )
			else:
				dbFilter.filter( name, unicode( rawFilter[name] ) )
		return( dbFilter )

	def buildDBSort( self, name, skel, dbFilter, rawFilter ):
		if "orderby" in list(rawFilter.keys()) and rawFilter["orderby"] == name:
			if not self.indexed:
				logging.warning( "Invalid ordering! %s is not indexed!" % name )
				raise RuntimeError()
			if self.caseSensitive:
				prop = name
			else:
				prop = name+"_idx"
			if "orderdir" in rawFilter.keys()  and rawFilter["orderdir"]=="1":
				order = ( prop, db.DESCENDING )
			else:
				order = ( prop, db.ASCENDING )
			inEqFilter = [ x for x in dbFilter.datastoreQuery.keys() if (">" in x[ -3: ] or "<" in x[ -3: ] or "!=" in x[ -4: ] ) ]
			if inEqFilter:
				inEqFilter = inEqFilter[ 0 ][ : inEqFilter[ 0 ].find(" ") ]
				if inEqFilter != order[0]:
					logging.warning("I fixed you query! Impossible ordering changed to %s, %s" % (inEqFilter, order[0]) )
					dbFilter.order( inEqFilter, order )
				else:
					dbFilter.order( order )
			else:
				dbFilter.order( order )
		return( dbFilter )

	def getSearchTags(self):
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
