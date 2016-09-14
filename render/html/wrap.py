#-*- coding: utf-8 -*-

class ListWrapper( list ):
	"""
		Monkey-Patching for lists.
		Allows collecting sub-properties by using []
		Example: [ {"key":"1"}, {"key":"2"} ]["key"] --> ["1","2"]
	"""
	def __init__( self, src ):
		"""
			Initializes this wrapper by copying the values from src
		"""
		self.extend( src )
	
	def __getitem__( self, key ):
		if isinstance( key, int ):
			return( super( ListWrapper, self ).__getitem__( key ) )
		res = []
		for obj in self:
			if isinstance( obj, dict ) and key in obj.keys():
				res.append( obj[ key ] )
			elif key in dir( obj ):
				res.append( getattr( obj, key ) )
		return( ListWrapper(res) )

class SkelListWrapper(ListWrapper):
	"""
		Like ListWrapper, but takes the additional properties
		of skellist into account - namely cursor and customQueryInfo.
	"""
	def __init__( self, src, origQuery=None ):
		super( SkelListWrapper, self ).__init__( src )
		if origQuery is not None:
			self.cursor = origQuery.cursor
			self.customQueryInfo = origQuery.customQueryInfo
		else:
			self.cursor = src.cursor
			self.customQueryInfo = src.customQueryInfo
