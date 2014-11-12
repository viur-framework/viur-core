# -*- coding: utf-8 -*-
from server.applications.list import List
from server.skeleton import SkelList
from server.bones import *
from server import errors, session, conf, request, exposed, internalExposed
from server import utils


class Cart( List ):
	listTemplate = "order_viewcart"
	adminInfo = None
	productSkel = None

	@exposed
	def add( self, product, amt=None, extend=False ):
		"""
		Adds the product with the id product to the cart.
		If product already exists, and amt is left-out, the number of the product in the cart will be increased.

		:param product: The product key to add to the cart.
		:param amt: The amount to add; default is 1.
		:param extend: Set True, if amt should be added to existing items, else the amount is overridden.
		"""

		prods = session.current.get("cart_products") or {}

		if not all( x in "1234567890" for x in unicode(amt) ):
			amt = None

		if self.productSkel().fromDB( product ):
			if not product in prods.keys():
				prods[ product ] = { "amount" : 0 }

			if amt and not extend:
				prods[ product ][ "amount" ] = int(amt)
			else:
				if amt is None:
					amt = 1

				prods[ product ][ "amount" ] += int( amt )

			session.current["cart_products"] = prods
			session.current.markChanged()

		raise( errors.Redirect( "/%s/view" % self.modulName ) )

	@exposed
	def view( self, *args, **kwargs ):
		prods = session.current.get("cart_products") or {}

		if prods:
			items = self.productSkel().all().mergeExternalFilter( {"id": list(prods.keys()) } ).fetch( limit=10 )
		else:
			items = SkelList( self.productSkel )

		for skel in items:
			skel["amt"] = numericBone( descr="Quantity",
			                defaultValue = session.current["cart_products"][ str( skel["id"].value ) ][ "amount" ] )

		return( self.render.list( items ) )

	@exposed
	def delete( self, product , all="0" ):
		prods = session.current.get("cart_products") or {}

		if product in prods.keys():
			if all=="0" and prods[ product ][ "amount" ] > 1:
				prods[ product ][ "amount" ] -= 1
			else:
				del prods[ product ]

		session.current["cart_products"] = prods
		session.current.markChanged()
		raise( errors.Redirect( "/%s/view" % self.modulName ) )

	@internalExposed
	def entryCount( self ):
		prods = session.current.get("cart_products") or {}
		return( len( prods.keys() ) )
