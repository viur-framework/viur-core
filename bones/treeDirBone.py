# -*- coding: utf-8 -*-
from server.bones import baseBone
from server import utils
from server import db

class treeDirBone( baseBone ):
	def __init__( self, type, multiple=False, *args, **kwargs ):
		super( treeDirBone, self ).__init__( type=type, *args, **kwargs )
		self.type = type
		self.multiple = multiple

	
	def findPathInRepository( self, repository, path ):
		dbObj = utils.generateExpandoClass(  )
		repo = db.Get( db.Key( repository ) )
		for comp in path.split("/"):
			if not repo:
				return( None )
			if not comp:
				continue			
			repo = db.Query( self.type+"_repository").filter( "parentdir =", str(repo.key()))\
					.filter( "name =", comp ).get()
		if not repo:
			return( None )
		else:
			return( repo )
	
		
	def fromClient( self, name, data ):
		"""
			Reads a value from the client.
			If this value is valis for this bone,
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
		if name in data.keys():
			value = data[ name ]
		else:
			value = None
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
							if valstr and not self.canUse(  valstr  ):
								res.append(  valstr )
					else:
						valstr =  value
						if valstr and not self.canUse(  valstr ):
							res.append( valstr )
			else:
				for val in value:
					valstr =  val 
					if valstr and not self.canUse( valstr  ):
						res.append( valstr )
		else:
			valstr = value 
			if valstr and not self.canUse( valstr ):
				res.append( valstr )
		if len( res ) == 0:
			return( "No value entered" )
		if self.multiple:
			self.value = res
		else:
			self.value = res[0]
		return( None )
	
	def canUse( self, value ):
		try:
			repo, path = value.split("/",1)
		except:
			return("Invalid value")
		path = "/"+path
		repo = self.findPathInRepository( repo, path )
		if not repo:
			return( "Invalid path supplied" )
		return( None )
		
	
	def unserialize( self, name, expando ):
		super( treeDirBone, self ).unserialize( name, expando )
		if self.multiple and not self.value:
			self.value = []
