# -*- coding: utf-8 -*-

class HTTPException( Exception ):
	def __init__( self, status, name, descr ):
		self.status = status
		self.name = name
		self.descr = descr
	
	def process( self ):
	    pass

class BadRequest( HTTPException ):
	def __init__( self, descr="The request your browser send cannot be fulfilled due to bad syntax." ):
		super( BadRequest, self ).__init__(  status=400, name = "Bad Request", descr=descr )

class Redirect( HTTPException ):
	def __init__( self, url, descr="Redirect", status=303 ):
		super( Redirect, self ).__init__(  status=303, name = "Redirect", descr=descr )
		self.url = url

class Unauthorized( HTTPException ):
	def __init__( self, descr="The resource is protected and you dont have the permissions." ):
		super( Unauthorized, self ).__init__(  status=401, name = "Unauthorized", descr=descr )

class PaymentRequired( HTTPException ):
	def __init__( self, descr="Payment Required" ):
		super( PaymentRequired, self ).__init__(  status=402, name = "Payment Required", descr=descr )

class Forbidden( HTTPException ):
	def __init__( self, descr="The resource is protected and you dont have the permissions." ):
		super( Forbidden, self ).__init__(  status=403, name = "Forbidden", descr=descr )

class NotFound( HTTPException ):
	def __init__( self, descr="The requested resource could not be found." ):
		super( NotFound, self ).__init__(  status=404, name = "Not Found", descr=descr )

class MethodNotAllowed( HTTPException ):
	def __init__( self, descr="Method Not Allowed" ):
		super( MethodNotAllowed, self ).__init__(  status=405, name = "Method Not Allowed", descr=descr )

class NotAcceptable( HTTPException ):
	def __init__( self, descr="The request cannot be processed due to missing or invalid parameters." ):
		super( NotAcceptable, self ).__init__(  status=406, name = "Not Acceptable", descr=descr )

class RequestTimeout( HTTPException ): #This must be used for the task api to indicate it should retry
	def __init__( self, descr="The request has timed out." ):
		super( RequestTimeout, self ).__init__(  status=408, name = "Request Timeout", descr=descr )

class Gone( HTTPException ):
	def __init__( self, descr="Gone" ):
		super( Gone, self ).__init__(  status=410, name = "Gone", descr=descr )

class PreconditionFailed( HTTPException ):
	def __init__( self, descr="Precondition Failed" ):
		super( PreconditionFailed, self ).__init__(  status=412, name = "Precondition Failed", descr=descr )
		
class RequestTooLarge( HTTPException ):
	def __init__( self, descr="Request Too Large" ):
		super( PreconditionFailed, self ).__init__(  status=413, name = "Request Too Large", descr=descr )

class InternalServerError( HTTPException ):
	def __init__( self, descr="Internal Server Error" ):
		super( Gone, self ).__init__(  status=500, name = "Internal Server Error", descr=descr )

class NotImplemented( HTTPException ):
	def __init__( self, descr="Not Implemented" ):
		super( NotImplemented, self ).__init__(  status=501, name = "Not Implemented", descr=descr )
		
class BadGateway( HTTPException ):
	def __init__( self, descr="Bad Gateway" ):
		super( BadGateway, self ).__init__(  status=502, name = "Bad Gateway", descr=descr )
		
class ServiceUnavailable( HTTPException ):
	def __init__( self, descr="Service Unavailable" ):
		super( ServiceUnavailable, self ).__init__(  status=503, name = "Service Unavailable", descr=descr )

