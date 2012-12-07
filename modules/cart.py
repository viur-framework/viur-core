# -*- coding: utf-8 -*-
from server.applications.list import List
from server.skellist import Skellist
from server.bones import *
from server import errors, session, conf, request
from server import utils
from google.appengine.ext import ndb


class Cart( List ):
	listTemplate = "order_viewcart"
	adminInfo = None
	productSkel = None
	
	def add( self, product, amt=None ):
		prods = session.current.get("cart_products") or {}
		if not all( x in "1234567890" for x in unicode(amt) ):
			amt = None
		if self.productSkel().fromDB( product ):
			if product in prods.keys():
				if amt:
					prods[ product ] = int(amt)
				else:
					prods[ product ] += 1
			else:
				if amt:
					prods[ product ] = int(amt)
				else:
					prods[ product ] = 1
			session.current["cart_products"] = prods
			session.current.markChanged()
		raise( errors.Redirect( "/cart/view" ) )
	add.exposed=True
	
	def view( self, *args, **kwargs ):
		prods = session.current.get("cart_products") or {}
		mylist = Skellist( self.productSkel )
		if prods:
			queryObj = utils.buildDBFilter( self.productSkel(), {} ) #Build the initial one
			queryObj = queryObj.filter(self.productSkel()._expando._key.IN( [ ndb.Key( urlsafe=x ) for x in list(prods.keys()) ] ) )
			queryObj.limit = 10
			queryObj.cursor = None
			mylist.fromDB( queryObj )
		for skel in mylist:
			skel.amt = numericBone( descr="Anzahl", defaultvalue=session.current["cart_products"][ str( skel.id.value ) ] )
		return( self.render.list( mylist ) )
	view.exposed=True
	
	
	def delete( self, product , all="0" ):
		prods = session.current.get("cart_products") or {}
		if product in prods.keys():
			if all=="0" and prods[ product ] > 1:
				prods[ product ] -= 1
			else:
				del prods[ product ]
		session.current["cart_products"] = prods
		session.current.markChanged()
		raise( errors.Redirect( "/cart/view" ) )
	delete.exposed=True
	
	def entryCount( self ):
		prods = session.current.get("cart_products") or {}
		return( len( prods.keys() ) )
	entryCount.internalExposed=True
