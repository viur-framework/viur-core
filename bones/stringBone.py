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

	def serialize( self, valuesCache, name, entity ):
		for k in entity.keys(): #Remove any old data
			if k.startswith("%s." % name ):
				del entity[ k ]
		if not self.languages:
			if self.caseSensitive:
				return( super( stringBone, self ).serialize( valuesCache, name, entity ) )
			else:
				if name != "key":
					entity.set( name, valuesCache[name], self.indexed )
					if valuesCache[name] is None:
						entity.set( name+".idx", None, self.indexed )
					elif isinstance( valuesCache[name], list ):
						entity.set( name+".idx", [unicode( x ).lower() for x in valuesCache[name]], self.indexed )
					else:
						entity.set( name+".idx", unicode( valuesCache[name] ).lower(), self.indexed )
		else: #Write each language separately
			if not valuesCache.get(name, None):
				return( entity )
			if isinstance( valuesCache[name], basestring ) or (isinstance( valuesCache[name], list ) and self.multiple): #Convert from old format
				lang = self.languages[0]
				entity.set( "%s.%s" % (name, lang), valuesCache[name], self.indexed )
				if not self.caseSensitive:
					if isinstance( valuesCache[name], basestring ):
						entity.set( "%s.%s.idx" % (name, lang), valuesCache[name].lower(), self.indexed )
					else:
						entity.set( "%s.%s.idx" % (name, lang), [x.lower for x in valuesCache[name]], self.indexed )
				# Fill in None for all remaining languages (needed for sort!)
				if self.indexed:
					for lang in self.languages[ 1: ]:
						entity.set( "%s.%s" % (name, lang), "", self.indexed )
						if not self.caseSensitive:
							entity.set( "%s.%s.idx" % (name, lang), "", self.indexed )
			else:
				assert isinstance( valuesCache[name], dict)
				for lang in self.languages:
					if lang in valuesCache[name].keys():
						val = valuesCache[name][ lang ]
						entity.set( "%s.%s" % (name, lang), valuesCache[name][lang], self.indexed )
						if not self.caseSensitive:
							if isinstance( val, basestring ):
								entity.set( "%s.%s.idx" % (name, lang), val.lower(), self.indexed )
							elif isinstance(val, list):
								entity.set("%s.%s.idx" % (name, lang), [x.lower() for x in val if isinstance(x, basestring)], self.indexed)
							else:
								logging.warning("Invalid type in serialize, got %s", str(type(val)))
					else:
						# Fill in None for all remaining languages (needed for sort!)
						if self.indexed:
							entity.set( "%s.%s" % (name, lang), "", self.indexed )
							if not self.caseSensitive:
								entity.set( "%s.%s.idx" % (name, lang), "", self.indexed )
		return( entity )

	def unserialize(self, valuesCache, name, expando):
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
				valuesCache[name] = expando[name]
		else:
			valuesCache[name] = LanguageWrapper( self.languages )
			for lang in self.languages:
				if "%s.%s" % ( name, lang ) in expando.keys():
					val = expando[ "%s.%s" % ( name, lang ) ]
					if isinstance( val, list ) and not self.multiple:
						val = ", ".join( val )
					valuesCache[name][lang] = val
			if not valuesCache[name].keys(): #Got nothing
				if name in expando.keys(): #Old (non-multi-lang) format
					valuesCache[name][ self.languages[0] ] = expando[ name ]
		return( True )

	def fromClient( self, valuesCache, name, data ):
		"""
			Reads a value from the client.
			If this value is valid for this bone,
			store this rawValue and return None.
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
			rawValue = data[ name ]
		else:
			rawValue = None
		res = None
		lastError = None
		if self.multiple and self.languages:
			res = LanguageWrapper(self.languages)
			for lang in self.languages:
				res[lang] = []
				if "%s.%s" % (name, lang) in data.keys():
					val = data["%s.%s" % (name, lang)]
					if isinstance(val, basestring):
						err = self.isInvalid(val)
						if not err:
							res[lang].append(utils.escapeString(val))
						else:
							lastError = err
					elif isinstance(val, list):
						for v in val:
							err = self.isInvalid(v)
							if not err:
								res[lang].append(utils.escapeString(v))
							else:
								lastError = err
			if not any(res.values()) and not lastError:
				lastError = "No rawValue entered"
		elif self.multiple and not self.languages:
			res = []
			if not rawValue:
				lastError = "No rawValue entered"
			else:
				if not isinstance( rawValue, list ):
					rawValue = [rawValue]
				for val in rawValue:
					err = self.isInvalid(val)
					if not err:
						res.append(utils.escapeString(val))
					else:
						lastError = err
				if len(res) > 0:
					res = res[0:254]  # Max 254 character 
				else:
					lastError = "No valid rawValue entered"
		elif not self.multiple and self.languages:
			res = LanguageWrapper( self.languages )
			for lang in self.languages:
				if "%s.%s" % (name, lang) in data.keys():
					val = data["%s.%s" % (name, lang)]
					err = self.isInvalid(val)
					if not err:
						res[lang] = utils.escapeString(val)
					else:
						lastError = err
			if len(res.keys())==0 and not lastError:
				lastError = "No rawValue entered"
		else:
			err = self.isInvalid(rawValue)
			if not err:
				res = utils.escapeString(rawValue)
			else:
				lastError = err
			if not rawValue and not lastError:
				lastError = "No rawValue entered"
		valuesCache[name] = res
		return lastError
				

	def buildDBFilter( self, name, skel, dbFilter, rawFilter, prefix=None ):
		if not name in rawFilter.keys() and not any( [(x.startswith(name+"$") or x.startswith(name+".")) for x in rawFilter.keys()] ):
			return( super( stringBone, self ).buildDBFilter( name, skel, dbFilter, rawFilter, prefix ) )
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
		if name+"$lk" in rawFilter.keys(): #Do a prefix-match
			if not self.caseSensitive:
				dbFilter.filter( (prefix or "")+namefilter +".idx >=", unicode( rawFilter[name+"$lk"] ).lower() )
				dbFilter.filter( (prefix or "")+namefilter +".idx <", unicode( rawFilter[name+"$lk"]+u"\ufffd" ).lower() )
			else:
				dbFilter.filter( (prefix or "")+namefilter + " >=", unicode( rawFilter[name+"$lk"] ) )
				dbFilter.filter( (prefix or "")+namefilter + " < ", unicode( rawFilter[name+"$lk"]+u"\ufffd" ) )
			hasInequalityFilter = True
		if name+"$gt" in rawFilter.keys(): #All entries after
			if not self.caseSensitive:
				dbFilter.filter( (prefix or "")+namefilter +".idx >", unicode( rawFilter[name+"$gt"] ).lower() )
			else:
				dbFilter.filter( (prefix or "")+namefilter + " >", unicode( rawFilter[name+"$gt"] ) )
			hasInequalityFilter = True
		if name+"$lt" in rawFilter.keys(): #All entries before
			if not self.caseSensitive:
				dbFilter.filter( (prefix or "")+namefilter +".idx <", unicode( rawFilter[name+"$lt"] ).lower() )
			else:
				dbFilter.filter( (prefix or "")+namefilter + " <", unicode( rawFilter[name+"$lt"] ) )
			hasInequalityFilter = True
		if name in rawFilter.keys(): #Normal, strict match
			if not self.caseSensitive:
				dbFilter.filter( (prefix or "")+namefilter+".idx", unicode( rawFilter[name] ).lower() )
			else:
				dbFilter.filter( (prefix or "")+namefilter, unicode( rawFilter[name] ) )
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

	def getSearchTags(self, valuesCache, name):
		res = []
		if not valuesCache[name]:
			return (res)
		value = valuesCache[name]
		if self.languages and isinstance(value, dict):
			if self.multiple:
				for lang in value.values():
					for val in lang:
						for line in unicode(val).splitlines():
							for key in line.split(" "):
								key = "".join([c for c in key if c.lower() in conf[
									"viur.searchValidChars"]])
								if key and key not in res and len(key) > 1:
									res.append(key.lower())
			else:
				for lang in value.values():
					for line in unicode(lang).splitlines():
						for key in line.split(" "):
							key = "".join([c for c in key if
							               c.lower() in conf["viur.searchValidChars"]])
							if key and key not in res and len(key) > 1:
								res.append(key.lower())
		else:
			if self.multiple:
				for val in value:
					for line in unicode(val).splitlines():
						for key in line.split(" "):
							key = "".join([c for c in key if
							               c.lower() in conf["viur.searchValidChars"]])
							if key and key not in res and len(key) > 1:
								res.append(key.lower())
			else:
				for line in unicode(value).splitlines():
					for key in line.split(" "):
						key = "".join(
							[c for c in key if c.lower() in conf["viur.searchValidChars"]])
						if key and key not in res and len(key) > 1:
							res.append(key.lower())

		return (res)

	def getSearchDocumentFields(self, valuesCache, name):
		"""
			Returns a list of search-fields (GAE search API) for this bone.
		"""
		res = []
		if self.languages:
			if valuesCache[name] is not None:
				for lang in self.languages:
					if lang in valuesCache[name].keys():
						res.append( search.TextField( name=name, value=unicode( valuesCache[name][lang]), language=lang ) ) 
		else:
			res.append( search.TextField( name=name, value=unicode( valuesCache[name] ) ) )
		return( res )

	def getUniquePropertyIndexValue(self, valuesCache, name):
		"""
			Returns an hash for our current value, used to store in the uniqueProptertyValue index.
		"""
		if not valuesCache[name] and not self.required: #Dont enforce a unique property on an empty string if we are required=False
			return( None )
		return( super( stringBone, self).getUniquePropertyIndexValue(valuesCache, name))

