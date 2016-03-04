# -*- coding: utf-8 -*-
from server.bones import baseBone
from server.config import conf
from server import db
from server import request
from server import utils
from server.session import current as currentSession
from google.appengine.api import search
import logging


class LanguageWrapper( dict ):
	"""
		Wrapper-class for a multi-language value.
		Its a dictionary, allowing accessing each stored language,
		but can also be used as a string, in which case it tries to
		guess the correct language.
	"""
	
	def __init__( self, languages ):
		super( LanguageWrapper, self ).__init__()
		self.languages = languages
	
	def __str__( self ):
		return( unicode(self.resolve()) )

	def resolve(self):
		"""
			Causes this wrapper to evaluate to the best language available for the current request.

			:returns: str|list of str
			:rtype: str|list of str
		"""
		lang = request.current.get().language # currentSession.getLanguage()
		if not lang:
			lang = self.languages[ 0 ]
		else:
			if lang in conf["viur.languageAliasMap"].keys():
				lang = conf["viur.languageAliasMap"][ lang ]
		if lang in self.keys() and self[ lang ] is not None and unicode( self[ lang ] ).strip(): #The users language is avaiable :)
			return( self[ lang ] )
		else: #We need to select another lang for him
			for lang in self.languages:
				if lang in self.keys() and self[ lang ]:
					return( self[ lang ] )
		return( "" )


class stringBone( baseBone ):
	type = "str"

	@staticmethod
	def generageSearchWidget(target,name="STRING BONE",mode="equals"):
		return ( {"name":name,"mode":mode,"target":target,"type":"string"} )

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
				if name != "key":
					entity.set( name, self.value, self.indexed )
					if self.value is None:
						entity.set( name+".idx", None, self.indexed )
					elif isinstance( self.value, list ):
						entity.set( name+".idx", [unicode( x ).lower() for x in self.value], self.indexed )
					else:
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
				# Fill in None for all remaining languages (needed for sort!)
				if self.indexed:
					for lang in self.languages[ 1: ]:
						entity.set( "%s.%s" % (name, lang), "", self.indexed )
						if not self.caseSensitive:
							entity.set( "%s.%s.idx" % (name, lang), "", self.indexed )
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
					else:
						# Fill in None for all remaining languages (needed for sort!)
						if self.indexed:
							entity.set( "%s.%s" % (name, lang), "", self.indexed )
							if not self.caseSensitive:
								entity.set( "%s.%s.idx" % (name, lang), "", self.indexed )
		return( entity )
		
	def unserialize( self, name, expando ):
		"""
			Inverse of serialize. Evaluates whats
			read from the datastore and populates
			this bone accordingly.

			:param name: The property-name this bone has in its :class:`server.skeleton.Skeleton` (not the description!)
			:type name: str
			:param expando: An instance of the dictionary-like db.Entity class
			:type expando: :class:`server.db.Entity`
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
			
			:param name: Our name in the :class:`server.skeleton.Skeleton`
			:type name: str
			:param data: *User-supplied* request-data
			:type data: dict
			:returns: str or None
		"""
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
						self.value[ lang ].append( utils.escapeString( val ) )
					elif isinstance( val, list ):
						for v in val:
							self.value[ lang ].append( utils.escapeString( v ) )
			if not any( self.value.values() ):
				return( "No value entered" )
			else:
				return( None )
		elif self.multiple and not self.languages:
			self.value = []
			if not value:
				return( "No value entered" )
			if not isinstance( value, list ):
				value = [value]
			for val in value:
				if not self.isInvalid( val ):
					self.value.append( utils.escapeString( val ) )
			if( len( self.value ) > 0):
				self.value = self.value[0:254] #Max 254 Keys
				return( None )
			else:
				return( "No valid value entered" )
		elif not self.multiple and self.languages:
			self.value = LanguageWrapper( self.languages )
			err = None
			for lang in self.languages:
				if "%s.%s" % ( name, lang ) in data.keys():
					val = data["%s.%s" % ( name, lang )]
					tmpErr = self.isInvalid( val )
					if not tmpErr:
						self.value[ lang ] = utils.escapeString( val )
					else:
						err = tmpErr
			if err:
				return( err )
			else:
				if len( self.value.keys() )==0: #No valid value
					return( "No value entered" )
			return( None )
			
		else:
			err = self.isInvalid( value )
			if not err:
				if not value:
					self.value = u""
					return( "No value entered" )
				self.value = utils.escapeString( value )
				return( None )
			else:
				return( err )

	def buildDBFilter( self, name, skel, dbFilter, rawFilter ):
		if not name in rawFilter.keys() and not any( [(x.startswith(name+"$") or x.startswith(name+".")) for x in rawFilter.keys()] ):
			return( super( stringBone, self ).buildDBFilter( name, skel, dbFilter, rawFilter ) )
		if not self.indexed:
			logging.warning( "Invalid searchfilter! %s is not indexed!" % name )
			raise RuntimeError()
		hasInequalityFilter = False
		if not self.languages:
			namefilter = name
		else:
			lang = None
			for key in rawFilter.keys():
				if key.startswith( "%s." % name ):
					langStr = key.replace( "%s." % name, "" )
					if langStr in self.languages:
						lang = langStr
						break
			if not lang:
				lang = request.current.get().language #currentSession.getLanguage()
				if not lang or not lang in self.languages:
					lang = self.languages[ 0 ]
			namefilter = "%s.%s" % (name, lang)
		if namefilter+"$lk" in rawFilter.keys(): #Do a prefix-match
			if not self.caseSensitive:
				dbFilter.filter( namefilter +".idx >=", unicode( rawFilter[namefilter+"$lk"] ).lower() )
				dbFilter.filter( namefilter +".idx <", unicode( rawFilter[namefilter+"$lk"]+u"\ufffd" ).lower() )
			else:
				dbFilter.filter( namefilter + " >=", unicode( rawFilter[namefilter+"$lk"] ) )
				dbFilter.filter( namefilter + " < ", unicode( rawFilter[namefilter+"$lk"]+u"\ufffd" ) )
			hasInequalityFilter = True
		if namefilter+"$gt" in rawFilter.keys(): #All entries after
			if not self.caseSensitive:
				dbFilter.filter( namefilter +".idx >", unicode( rawFilter[namefilter+"$gt"] ).lower() )
			else:
				dbFilter.filter( namefilter + " >", unicode( rawFilter[namefilter+"$gt"] ) )
			hasInequalityFilter = True
		if namefilter+"$lt" in rawFilter.keys(): #All entries before
			if not self.caseSensitive:
				dbFilter.filter( namefilter +".idx <", unicode( rawFilter[namefilter+"$lt"] ).lower() )
			else:
				dbFilter.filter( namefilter + " <", unicode( rawFilter[namefilter+"$lt"] ) )
			hasInequalityFilter = True
		if namefilter in rawFilter.keys(): #Normal, strict match
			if not self.caseSensitive:
				dbFilter.filter( namefilter+".idx", unicode( rawFilter[namefilter] ).lower() )
			else:
				dbFilter.filter( namefilter, unicode( rawFilter[namefilter] ) )
		return( dbFilter )

	def buildDBSort( self, name, skel, dbFilter, rawFilter ):
		if "orderby" in list(rawFilter.keys()) and (rawFilter["orderby"] == name or (isinstance(rawFilter["orderby"], basestring) and rawFilter["orderby"].startswith("%s."%name) and self.languages)):
			if not self.indexed:
				logging.warning( "Invalid ordering! %s is not indexed!" % name )
				raise RuntimeError()
			if self.languages:
				lang = None
				if rawFilter["orderby"].startswith("%s."%name):
					lng = rawFilter["orderby"].replace("%s."%name,"")
					if lng in self.languages:
						lang = lng
				if lang is None:
					lang = request.current.get().language #currentSession.getLanguage()
					if not lang or not lang in self.languages:
						lang = self.languages[ 0 ]
				if self.caseSensitive:
					prop = "%s.%s" % (name, lang)
				else:
					prop = "%s.%s.idx" % (name, lang)
			else:
				if self.caseSensitive:
					prop = name
				else:
					prop = name+".idx"
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
		if self.languages and isinstance( value, dict ):
			for lang in value.values():
				for line in unicode(lang).splitlines():
					for key in line.split(" "):
						key = "".join( [ c for c in key if c.lower() in conf["viur.searchValidChars"] ] )
						if key and key not in res and len(key)>3:
							res.append( key.lower() )
		else:
			for line in unicode(value).splitlines():
				for key in line.split(" "):
					key = "".join( [ c for c in key if c.lower() in conf["viur.searchValidChars"] ] )
					if key and key not in res and len(key)>3:
						res.append( key.lower() )
		return( res )

	def getSearchDocumentFields(self, name):
		"""
			Returns a list of search-fields (GAE search API) for this bone.
		"""
		res = []
		if self.languages:
			if self.value is not None:
				for lang in self.languages:
					if lang in self.value.keys():
						res.append( search.TextField( name=name, value=unicode( self.value[lang]), language=lang ) ) 
		else:
			res.append( search.TextField( name=name, value=unicode( self.value ) ) )
		return( res )

	def getUniquePropertyIndexValue( self ):
		"""
			Returns an hash for our current value, used to store in the uniqueProptertyValue index.
		"""
		if not self.value and not self.required: #Dont enforce a unique property on an empty string if we are required=False
			return( None )
		return( super( stringBone, self).getUniquePropertyIndexValue())

