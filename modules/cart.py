# -*- coding: utf-8 -*-
from server.prototypes.list import List
from server.skeleton import SkelList
from server.bones import *
from server import errors, session, conf, request, exposed, internalExposed
import json

class Cart(List):
	"""
	Implements a cart module which can be used in combination with the order module.
	"""


	listTemplate = "order_viewcart"
	adminInfo = None
	productSkel = None

	@exposed
	def add(self, product, amt=None, extend=False, async=False):
		"""
		Adds the product with the key product to the cart.

		If product already exists, and amt is left-out, the number of the products in the cart
		will be increased.

		:param product: The product key to add to the cart.
		:type product: str

		:param amt: The amount to add; defaults to 1.
		:type amt: str | int

		:param extend: Set True, if amt should be added to existing items, else the amount is
		overridden.
		:type extend: bool

		:param async: Set True for use in Ajax requests.
		:type extend: bool
		"""

		prods = session.current.get("cart_products") or {}

		# sanity checks
		if not isinstance(extend, bool):
			try:
				extend = bool(int(extend))
			except ValueError:
				extend = False

		if not isinstance(async, bool):
			try:
				async = bool(int(async))
			except ValueError:
				async = False

		if not (amt and all(x in "1234567890" for x in unicode(amt)) and int(amt) > 0):
			amt = None

		if self.productSkel().fromDB( product ):
			if not product in prods.keys():
				prods[ product ] = { "amount" : 0 }

			if amt and not bool( extend ):
				prods[ product ][ "amount" ] = int(amt)
			else:
				if not amt:
					amt = 1

				prods[ product ][ "amount" ] += int(amt)

			session.current["cart_products"] = prods
			session.current.markChanged()

		if async:
			return json.dumps({ "cartentries": self.entryCount(),
			                    "cartsum": self.cartSum(),
			                    "added": int( amt ) } )

		raise errors.Redirect("/%s/view" % self.moduleName)

	@exposed
	def view(self, *args, **kwargs):
		"""
		Views the current cart content.
		"""

		prods = session.current.get("cart_products") or {}

		if prods:
			items = self.productSkel().all().mergeExternalFilter( {"key": list(prods.keys()) } ).fetch(limit=10)
		else:
			items = SkelList( self.productSkel )

		for skel in items:
			skel["amt"] = numericBone(
							descr="Quantity",
							defaultValue=session.current["cart_products"][str(skel["key"].value)]["amount"])

		return self.render.list(items)

	@exposed
	def delete(self, product, all="0", async=False):
		"""
		Deletes or decrements a product from the cart.
		If all is set, it removes the entire product.

		:param product: The product key to add to the cart.
		:type product: str

		:param all: If not "0", remove the entire entry for product, else decrement.
		:type all: str

		:param async: Set True for use in Ajax requests.
		:type async: bool
		"""

		prods = session.current.get("cart_products") or {}

		if product in prods.keys():
			removed = prods[ product ][ "amount" ]

			if all=="0" and prods[ product ][ "amount" ] > 1:
				prods[ product ][ "amount" ] -= 1
			else:
				del prods[ product ]
		else:
			removed = 0

		session.current["cart_products"] = prods
		session.current.markChanged()

		if async:
			return json.dumps({ "cartentries": self.entryCount(),
			                    "cartsum": self.cartSum(),
			                    "removed": removed })

		raise errors.Redirect("/%s/view" % self.moduleName)

	@internalExposed
	def entryCount( self ):
		"""
		Returns the products in the cart.

		:return: Number of products.
		:rtype: int
		"""

		prods = session.current.get("cart_products") or {}
		return len(prods.keys())

	@internalExposed
	def cartSum( self ):
		"""
		This function should be overridden, to return the current cart total sum.

		:return: Current cart total. Default implementation always returns 0.0
		:rtype: float
		"""
		return 0.0
