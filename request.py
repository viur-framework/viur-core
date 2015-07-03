# -*- coding: utf-8 -*-
import threading


class RequestWrapper( object ):
	"""
		Request Wrapper.
		Allows applications to access the current request
		object (google.appengine.ext.webapp.Request)
		without having a direct reference to it.
		Use singleton 'current' instead of this class.

		Example::

			from request import current as currentRequest
			currentRequest.get().headers
	"""
		
	def __init__( self,  *args, **kwargs ):
		super( RequestWrapper, self ).__init__( *args, **kwargs )
		self.data = threading.local()
	
	def setRequest(self, request ):
		self.data.request = request
		self.data.reqData = {}

	def get( self ):
		return( self.data.request )
	
	def requestData( self ):
		return( self.data.reqData )

current = RequestWrapper()
