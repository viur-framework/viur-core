# -*- coding: utf-8 -*-
import server
from server.applications.list import List
from server.skeleton import Skeleton
from server.bones import *
from server import errors, session, conf, request, exposed, internalExposed
from server import securitykey
from server.tasks import callDeferred
from server import db, request
import urllib
import hashlib
from google.appengine.api import urlfetch
import logging
import re
from server import request
from datetime import datetime, timedelta
from server.tasks import PeriodicTask


class OrderSkel( Skeleton ):
	kindName = "order"
	bill_gender = selectOneBone( descr=u"Bill-gender", required=True, values={"male":"Mr.", "female":"Mrs."} )
	bill_firstname = stringBone( descr=u"Bill-first name", params={"indexed": True, "frontend_list_visible": True},required=True,unsharp=True )
	bill_lastname = stringBone( descr=u"Bill-last name", params={"indexed": True, "frontend_list_visible": True},required=True,unsharp=True )
	bill_street = stringBone( descr=u"Bill-street", params={"indexed": True, "frontend_list_visible": True},required=True )
	bill_city = stringBone( descr=u"Bill-city",required=True )
	bill_zip = stringBone( descr=u"Bill-zipcode",required=True,unsharp=True )
	bill_country = selectCountryBone( descr=u"Bill-country", codes=selectCountryBone.ISO2, required=True)
	bill_email = emailBone( descr=u"email", required=True, unsharp=True)
	shipping_firstname = stringBone( descr=u"Shipping-first name", params={"indexed": True, "frontend_list_visible": True},required=True,unsharp=True )
	shipping_lastname = stringBone( descr=u"Shipping-last name", params={"indexed": True, "frontend_list_visible": True},required=True,unsharp=True )
	shipping_street = stringBone( descr=u"Shipping-street", params={"indexed": True, "frontend_list_visible": True},required=True )
	shipping_city = stringBone( descr=u"Shipping-city",required=True )
	shipping_zip = stringBone( descr=u"Shipping-zipcode",required=True,unsharp=True )
	shipping_country = selectCountryBone( descr=u"Shipping-country", codes=selectCountryBone.ISO2, required=True )
	extrashippingaddress = booleanBone( descr=u"Use alternative Shipment-Address", required=True)
	price = numericBone( descr=u"Grand total", precision=2, required=True, readOnly=True, indexed=True )
	state_complete = selectOneBone( descr=u"Complete", values={"0":"No","1":"Yes"}, defaultValue=0, readOnly=True, required=True, visible=False, indexed=True )
	state_payed = selectOneBone( descr=u"Paid", values={"0":"No","1":"Yes"}, defaultValue=0, readOnly=True, required=True, visible=False, indexed=True )
	state_send = selectOneBone( descr=u"Send", values={"0":"No","1":"Yes"}, defaultValue=0, readOnly=True, required=True, visible=False, indexed=True )
	state_rts = selectOneBone( descr=u"Ready to ship", values={"0":"No","1":"Yes"}, defaultValue=0, readOnly=True, required=True, visible=False, indexed=True )
	state_canceled = selectOneBone( descr=u"Canceled", values={"0":"No","1":"Yes"}, defaultValue=0, readOnly=True, required=True, visible=False, indexed=True )
	state_archived = selectOneBone( descr=u"Archived", values={"0":"No","1":"Yes"}, defaultValue=0, readOnly=True, required=True, visible=False, indexed=True )
	idx = numericBone( descr=u"Order-number", required=True, readOnly=True, params={"indexed": True, "frontend_list_visible": True}, indexed=True )
	shipping_type = selectOneBone( descr=u"Type of shipment", values={"0":"uninsured", "1":"insured"} , required=True)
	payment_type  = selectOneBone( descr=u"Type of payment", values={"prepaid":"Bank-transfer", "pod":"Pay on Deliver", "paypal":"Paypal", "sofort":"Sofort"} , required=True)

	subSkels = {	"billaddress":["bill_*","extrashippingaddress"],
		    	"shippingaddress": ["shipping_*"],
			"shiptype": ["shipping_type","payment_type"]
		    }

class SkipStepException( Exception ):
	"""Raise this Exception to skip the current step"""
	pass

class ReturnHtmlException( Exception ):
	"""Raise this Exception to force the return of the given HTML inside a pre/post handler"""
	def __init__(self, html ):
		super( ReturnHtmlException, self ).__init__()
		self.html = html

from server.modules.order_paypal import PayPal
from server.modules.order_sofort import Sofort

class Order( List ):
	"""
	Provides an unified orderingprocess with payment-handling.
	This is encoded as a state machine.
	"""

	archiveDelay = timedelta( days=31 ) # Archive completed orders after 31 Days
	paymentProviders = [PayPal,Sofort]

	states = [	"complete", # The user completed all steps of the process, he might got redirected to a paymentprovider
			"payed", #This oder has been payed
			"rts", #Ready to Ship
			"send", # Goods got shipped
			"canceled",  # Order got canceled
			"archived"  #This order has been executed
			]

	adminInfo = {
		"name": "Orders", #Name of this modul, as shown in ViUR Admin (will be translated at runtime)
		"handler": "list.order",  #Which handler to invoke
		"icon": "icons/modules/cart.svg", #Icon for this modul
		"filter":{"orderby":"creationdate","orderdir":1,"state_complete":"1" }, 
		"columns":["idx","bill_firstname","bill_lastname","amt","price","creationdate"],
		"views" : [	{ "name": u"Not shipped", "filter":{"state_archived": "0",  "state_complete":"1", "state_send":"0", "state_canceled":"0", "orderby":"creationdate","orderdir":1 }, "icon":"icons/status/order_not_shipped.svg", "columns":["idx","bill_firstname","bill_lastname","amt","price","creationdate"]},
				{ "name": u"Unpaid", "filter":{"state_archived": "0", "state_complete":"1", "state_payed":"0","state_canceled":"0", "orderby":"creationdate","orderdir":1}, "icon":"icons/status/order_unpaid.svg", "columns":["idx","bill_firstname","bill_lastname","amt","price","creationdate"] },
				{ "name": u"Paid","filter":{"state_archived": "0", "state_complete":"1", "state_payed":"1", "state_canceled":"0", "orderby":"creationdate","orderdir":1}, "icon":"icons/status/order_paid.svg", "columns":["idx","bill_firstname","bill_lastname","amt","price","creationdate"] },
				{ "name": u"Shipped", "filter":{"state_archived": "0", "state_complete":"1", "state_canceled":"0", "state_send":"1","orderby":"changedate","orderdir":1}, "icon":"icons/status/order_shipped.svg", "columns":["idx","bill_firstname","bill_lastname","amt","price","creationdate"] },
				{ "name": u"Ready to ship", "filter":{"state_archived": "0","state_canceled":"0",  "state_complete":"1", "state_send":"0","state_rts":"1","orderby":"changedate","orderdir":1}, "icon":"icons/status/order_ready.svg", "columns":["idx","bill_firstname","bill_lastname","amt","price","creationdate"] },
				{ "name": u"Canceled", "filter":{"state_archived": "0", "state_canceled":"1", "state_complete":"1",  "orderby":"changedate","orderdir":1}, "icon":"icons/status/order_cancelled.svg", "columns":["idx","bill_firstname","bill_lastname","amt","price","creationdate"] },
				{ "name": u"Archived", "filter":{"state_archived": "1", "state_complete":"1", "orderby":"changedate","orderdir":1}, "icon":"icons/status/archived.svg", "columns":["idx","bill_firstname","bill_lastname","amt","price","creationdate"] }
			]
		}


	def __init__(self, *args, **kwargs):
		super( Order, self ).__init__( *args, **kwargs )

		# Initialize the payment-providers
		self.initializedPaymentProviders = {}

		for p in self.paymentProviders:
			pInstance = p( self )
			self.initializedPaymentProviders[ pInstance.__class__.__name__.lower() ] = pInstance
			#Also put it as an object into self, sothat any exposed function is reachable
			setattr( self, "pp_%s" % pInstance.__class__.__name__.lower(), pInstance )

	def setState( self, orderID, state, removeState=False ):
		"""
			Set an status on the given order.
			
			@param orderID: ID of the order
			@type orderID: string
			@param state: An state out of self.states
			@type state: string
			@param removeState: Should the state be removed instead of set
			@type removeState: bool
		"""
		def txn( orderID, state, removeState ):
			dbObj = db.Get( db.Key( orderID ) )
			if not dbObj:
				return
			dbObj[ "state_%s" % state ] = "1" if not removeState else "0"
			dbObj["changedate"] = datetime.now()
			db.Put( dbObj )

		db.RunInTransaction( txn, orderID,  state, removeState )

	def getStates(self, orderID ):
		"""
			Returns the states currently set for the given order
			@param orderID: ID of the order
			@type orderID: string
			@returns: [string]
		"""
		dbObj = db.Get( db.Key( orderID ) )
		res = []

		if not dbObj:
			return( res )

		for state in self.states:
			stateName = "state_%s" % state

			if stateName in dbObj.keys() and str( dbObj[ stateName ] )=="1":
				res.append( state )

		return( res )
	
	def setComplete( self, orderID ):
		"""
		Marks an order as Complete
		May be overridden to hook this event
		
		@type orderID: string
		@param orderID: order to mark completed
		"""
		order = self.editSkel()

		if not order.fromDB( str(orderID) ):
			return( False )

		self.setState( orderID, "complete")

		if order[ "payment_type" ].value == "pod":
			states = self.getStates( orderID )

			if not any( [ x in states for x in ["canceled", "rts", "send"] ] ):
				self.setRTS( orderID )

		self.assignBillSequence( str(orderID) )
		return( True )

	def setRTS(self, orderID):
		"""
			Marks an order ready to send
			May be overridden to hook this event
			
			@type orderID: string
			@param orderID: order to mark
		"""
		self.setState( orderID, "rts")


	def setPayed(self, orderID):
		"""
		Marks an order as Payed
		May be overridden to hook this event

		@type orderID: string
		@param orderID: order to mark completed
		"""
		self.setState( orderID, "payed")
		states = self.getStates( orderID )

		if not any( [ x in states for x in ["rts", "send", "canceled", "closed"] ] ):
			self.setState( orderID,"rts")

		self.sendOrderPayedEMail( orderID )
		return( True )

	def setSend(self, orderID):
		"""
		Marks an order as Shiped
		May be overridden to hook this event

		@type orderID: string
		@param orderID: order to mark completed
		"""
		self.setState( orderID, "send" )
		self.setState( orderID, "rts", True )
		self.sendOrderShippedEMail( orderID )
		return( True )

	def setCanceled(self, orderID):
		"""
		Marks an order as Canceled
		May be overridden to hook this event

		@type orderID: string
		@param orderID: order to mark completed
		"""
		self.setState( orderID, "canceled" )
		self.setState( orderID, "rts", True )
		self.sendOrderCanceledEMail( orderID )
		return( True )
	
	def setArchived(self, orderID ):
		"""
		Marks an order as Archived
		May be overridden to hook this event

		@type orderID: string
		@param orderID: order to mark completed
		"""
		self.setState( orderID, "archived" )
		self.setState( orderID, "rts", True )
		self.sendOrderArchivedEMail( orderID )
		return( True )

	def sendOrderShippedEMail(self, orderID):
		pass

	def sendOrderCompleteEMail(self, orderID):
		pass
	
	def sendOrderPayedEMail(self, orderID):
		pass
	
	def sendOrderCanceledEMail(self, orderID):
		pass
	
	def sendOrderArchivedEMail(self, orderID):
		pass

	@exposed
	def markPayed( self, id, skey, *args, **kwargs ):
		if not self.canEdit( id ):
			raise errors.Unauthorized()
		if not securitykey.validate( skey ):
			raise errors.PreconditionFailed()
		self.setPayed( id )
		return("OKAY")

	@exposed
	def markSend( self, id, skey, *args, **kwargs ):
		if not self.canEdit( id ):
			raise errors.Unauthorized()

		if not securitykey.validate( skey ):
			raise errors.PreconditionFailed()

		self.setSend( id )
		return("OKAY")

	@exposed
	def markCanceled( self, id, skey, *args, **kwargs ):
		if not self.canEdit( id ):
			raise errors.Unauthorized()

		if not securitykey.validate( skey ):
			raise errors.PreconditionFailed()

		self.setCanceled( id )
		return("OKAY")

	def checkSkipShippingAddress( self, step, orderID, *args, **kwargs ):
		"""
		This step updates the current order copys the values from 
		billAddressSkel to shippingAddressSkel if extrashippingaddress is False
		
		@type step: int
		@param step: Current step within the ordering process
		@type orderID: string
		@param orderID: order to mark completed
		"""
		billSkel = self.editSkel()
		billSkel.fromDB( orderID )

		if not billSkel[ "extrashippingaddress" ].value:
			for name, bone in billSkel.items():
				if name.startswith( "bill_" ):
					name = name.replace( "bill_", "shipping_" )
					if name in billSkel.keys():
						billSkel[ name ].value = bone.value

			billSkel.toDB()
			raise SkipStepException()

	def calculateOrderSum( self, step, orderID, *args, **kwargs ):
		"""
		Calculates the final price for this order.
		*Must* be called before any attempt is made to start a payment process
		
		@type step: int
		@param step: Current step within the ordering process
		@type orderID: string
		@param orderID: order to calculate the price for
		"""
		price = sum( [x[3] for x in self.getBillItems( orderID ) ] )
		orderObj = db.Get( db.Key( str( orderID ) ) )
		orderObj["price"] = price
		db.Put( orderObj )

	def startPayment( self, step, orderID, *args, **kwargs ):
		"""
		Starts the payment processing for this order.
		The order is marked completed, so no further changes can be made.
		
		@type step: int
		@param step: Current step within the ordering process
		@type orderID: string
		@param orderID: order to mark completed
		"""
		order = self.editSkel()
		order.fromDB( orderID )
		if not str( order["state_complete"].value ) == "1":
			session.current["order_"+order.kindName] = None
			session.current.markChanged() #Fixme
			self.setComplete( orderID )
			if order[ "payment_type" ].value in self.initializedPaymentProviders.keys():
				pp = self.initializedPaymentProviders[ order[ "payment_type" ].value ]
				pp.startProcessing( step, orderID )
				#getattr( self, "paymentProvider_%s" % order.payment_type.value )( step, orderID )
	
	def paymentProvider_pod( self, step, orderID ):
		"""
			If Pay-On-Delivery is choosen, immediately mark this order as ready to ship
		"""
		self.setRTS( orderID )

	@internalExposed
	def getBillItems(self, orderID ):
		"""
		Returns all items for the given Order.
		Must be overridden.

		@type orderID: string
		@param orderID: order to mark completed
		@return: [ ( int Amount, Unicode Description , Float Price of one Item, Float Price of all Items (normaly Price of one Item*Amount), Float Included Tax )  ] 
		"""
		return( [] )
	
	def billSequenceAvailable( self, orderID ):
		self.sendOrderCompleteEMail( orderID )
	
	@callDeferred
	def assignBillSequence( self, orderID ):
		"""Assigns an unique order-order to the given Order """

		def  getIDtxn( kindName, orderID ):
			"""Generates and returns a new, unique ID"""
			seqObj = db.GetOrInsert( kindName," viur_bill_sequences", count=1000)
			idx = seqObj["count"]
			seqObj["count"] += 1
			db.Put( seqObj )
			return( str(idx) )

		def setIDtxn( orderID, idx ):
			"""Assigns the new order to the given order"""
			dbObj = db.Get( db.Key( orderID ) )
			if not dbObj:
				return
			dbObj[ "idx" ] = idx
			db.Put( dbObj )
		dbObj = db.Get( db.Key( orderID ) )
		if not dbObj:
			return
		idx = db.RunInTransaction( getIDtxn, self.viewSkel().kindName, orderID )
		db.RunInTransaction( setIDtxn, orderID, idx  )
		self.billSequenceAvailable( orderID )

	def rebuildSeachIndex(self, step, orderID, *args, **kwargs ):
		"""
			This rewrites the order after its completion.
			
			As each step has its own (tiny) skeleton, the searchIndex saved is incomplete.
			This loads the order using the (hopefully complete) viewSkel and saves it back,
			so that it is ensuring a complete searchIndex.
			
			Not a transaction, do not defer!
		"""
		skel = self.viewSkel()
		if not skel.fromDB( orderID ):
			raise AssertionError()
		skel.toDB()
	
	def resetCart(self, step, orderID, *args, **kwargs ):
		"""
			Clears the cart (if any) after the checkout
			process is finished.
		"""
		session.current["cart_products"] = None
		session.current.markChanged()
	
	def getSkelByName(self, name, orderID):
		"""
			Returns a skeleton for the given Name.
		"""
		if not name:
			return( self.viewSkel() )

		return( self.viewSkel().subSkel(name))

	def tmpSkipCheck(self, *args, **kwargs):
		raise SkipStepException()

	steps = 	[
				{
					"preHandler": tmpSkipCheck,
					"mainHandler": {
						"action": "function",
						"function": tmpSkipCheck
					}
				},
				{	
					"mainHandler": {
						"action": "edit", 
						"skeleton": "billaddress",
						"template": "order_billaddress", 
						"descr":u"Billinginformation"
					}
				}, 
				{	
					"preHandler": checkSkipShippingAddress,
					"mainHandler": {
						"action": "edit", 
						"skeleton": "shippingaddress",
						"template": "order_shipaddress", 
						"descr":u"Shippinginformation"
					}
				}, 
				{	
					"mainHandler": {
						"action": "edit", 
						"skeleton": "shiptype",
						"template": "order_payment", 
						"descr":u"Payment"
					}, 
					"postHandler": calculateOrderSum
				}, 
				{	
					"mainHandler": {
						"action": "view", 
						"skeleton": "",
						"template": "order_verify", 
						"descr":u"Overview"
					}
				}, 
				{	
					"preHandler": [rebuildSeachIndex,resetCart,startPayment], 
					"mainHandler": {
						"action": "view", 
						"skeleton": "",
						"template": "order_complete",
						"descr":u"Order completed"
					}
				}
			]
	
	@internalExposed
	def getSteps(self):
		steps = []
		for step in self.steps[:]:
			step = step.copy()
			step["mainHandler"] = step["mainHandler"].copy()
			if "descr" in step["mainHandler"]:
				step["mainHandler"].update({"descr": _(step["mainHandler"]["descr"])})
			steps.append( step )

		return steps
	
	def getBillPdf(self, orderID):
		"""
			Should be overridden to return the bill (as pdf) for the given order.
			
			@param orderID: Order, for which the the bill should be generated.
			@type orderID: str
			@returns: Bytes or None
		"""
		return( None )

	def getDeliveryNotePdf(self, orderID ):
		"""
			Should be overridden to return the delivery note (as pdf) for the given order.
			
			@param orderID: Order, for which the the bill of delivery should be generated.
			@type orderID: str
			@returns: Bytes or None
		"""
		return( None )
	
	@exposed
	def getBill(self, id, *args, **kwargs):
		"""
			Returns the Bill for the given order.
		"""
		skel = self.viewSkel()

		if "canView" in dir( self ):
			if not self.canView( id ):
				raise errors.Unauthorized()
		else:
			queryObj = self.viewSkel().all().mergeExternalFilter( {"id":  id} )
			queryObj = self.listFilter( queryObj ) #Access control

			if queryObj is None:
				raise errors.Unauthorized()

		bill = self.getBillPdf( id )

		if not bill:
			raise errors.NotFound()

		request.current.get().response.headers['Content-Type'] = "application/pdf"

		return( bill )

	@exposed
	def getDeliveryNote(self, id, *args, **kwargs):
		"""
			Returns the delivery note for the given order.
		"""
		skel = self.viewSkel()

		if "canView" in dir( self ):
			if not self.canView( id ):
				raise errors.Unauthorized()
		else:
			queryObj = self.viewSkel().all().mergeExternalFilter( {"id":  id} )
			queryObj = self.listFilter( queryObj ) #Access control

			if queryObj is None:
				raise errors.Unauthorized()

		bill = self.getDeliveryNotePdf( id )

		if not bill:
			raise errors.NotFound()

		request.current.get().response.headers['Content-Type'] = "application/pdf"
		return( bill )
	
	@exposed
	def checkout( self, step=None, id=None, skey=None, *args, **kwargs ):
		"""
		Performs the checkout process trough the state machine provided by self.steps.

		:param step: The current step index, None for beginning a new checkout
		:param id: Id of the current checkout
		:param skey: Server security key
		:return: Returns the rendered template or throws redirection exceptions.
		"""

		myKindName = self.viewSkel().kindName

		if step is None:
			logging.info("Starting new checkout process")
			billObj = db.Entity( myKindName )
			billObj["idx"] = "0000000"
			for state in self.states:
				billObj[ "state_%s" % state ] = "0"
			db.Put( billObj )
			id = str( billObj.key() )

			#Copy the Cart
			if "amountSkel" in dir ( self ):
				cart = session.current.get("cart_products") or {}
				s = self.amountSkel()
				products = []
				for prod, atts in cart.items():
					for i in range( 0, atts[ "amount" ] ):
						products.append( str(prod) )

				s.fromClient( {"product": products} )
				s.toDB()

			session.current["order_"+myKindName] = {"id": str( id ), "completedSteps": [] }
			session.current.markChanged()

			raise errors.Redirect( "?step=0&id=%s" % str( id ) )

		elif id:
			try:
				orderID = db.Key( id )
				step = int( step )
				assert( step>=0 )
				assert( step < len( self.steps ) )
			except:
				raise errors.NotAcceptable()

			sessionInfo = session.current.get("order_"+myKindName)

			if not sessionInfo or not sessionInfo.get("id") == str( orderID ):
				raise errors.Unauthorized()

			if step in sessionInfo["completedSteps"]:
				session.current["order_"+myKindName]["completedSteps"] = [ x for x in sessionInfo["completedSteps"] if x<step ]
				session.current.markChanged()

			#Make sure that no steps can be skipped
			if step != 0 and not step-1 in sessionInfo["completedSteps"]  :
				raise errors.Redirect("?step=0&id=%s" % str( str(orderID) ) )

			currentStep = self.steps[ step ]
			res = ""

			if "preHandler" in currentStep.keys():
				try:
					if isinstance( currentStep["preHandler"], list ):
						for handler in currentStep["preHandler"]:
							handler( self, step, str(orderID), *args, **kwargs )
					else:
						currentStep["preHandler"]( self, step, str(orderID),
						                           refkwargs=kwargs, *args, **kwargs )

				except SkipStepException:
					session.current["order_"+myKindName]["completedSteps"].append( step )
					session.current.markChanged()
					raise errors.Redirect("?step=%s&id=%s" % ( str( step+1 ), str( orderID ) ) )
				except ReturnHtmlException as e:
					return( e.html )

			if "requiresSecutityKey" in currentStep.keys() and currentStep["requiresSecutityKey"] :
				if not securitykey.validate( skey ):
					raise errors.PreconditionFailed()
				pass

			if "mainHandler" in currentStep.keys():

				if currentStep["mainHandler"]["action"] == "edit":
					skel = self.getSkelByName( currentStep["mainHandler"]["skeleton"], str(orderID) )
					skel.fromDB( str( orderID ) )

					if not len( kwargs.keys() ) or not skel.fromClient( kwargs ):
						return( self.render.edit( skel, tpl=currentStep["mainHandler"]["template"], step=step ) )

					skel.toDB()

				if currentStep["mainHandler"]["action"] == "view":
					if not "complete" in kwargs or not kwargs["complete"]==u"1":
						skel = self.getSkelByName( currentStep["mainHandler"]["skeleton"], str(orderID) )
						skel.fromDB( str( orderID ) )
						return( self.render.view( skel, tpl=currentStep["mainHandler"]["template"], step=step ) )
				elif currentStep["mainHandler"]["action"] == "function":
					res = currentStep["mainHandler"]["function"]( self, step, str(orderID), *args, **kwargs )
					if res:
						return( res )

			if "postHandler" in currentStep.keys():
				currentStep["postHandler"]( self, step, str(orderID), *args, **kwargs )

			session.current["order_"+myKindName]["completedSteps"].append( step )
			session.current.markChanged()

			logging.info( "next ?step=%s&id=%s" % (str( step+1 ), str( orderID ) ) )
			raise errors.Redirect("?step=%s&id=%s" % (str( step+1 ), str( orderID ) ) )

	def archiveOrder(self, order ):
		self.setState( order.key.urlsafe(), "archived" )
		self.sendOrderArchivedEMail( order.key.urlsafe() )
		logging.error("Order archived: "+str( order.key.urlsafe() ) )

	@PeriodicTask(60*24)
	def startArchiveOrdersTask( self, *args, **kwargs ):
		self.doArchiveActiveOrdersTask( (datetime.now()-self.archiveDelay).strftime("%d.%m.%Y %H:%M:%S"), None )
		self.doArchiveCancelledOrdersTask( (datetime.now()-self.archiveDelay).strftime("%d.%m.%Y %H:%M:%S"), None )

	@callDeferred
	def doArchiveActiveOrdersTask(self, timeStamp, cursor):
		logging.debug("Archiving old orders")

		#Archive all payed,send and not canceled orders
		query = self.viewSkel().all()\
				.filter( "changedate <", datetime.strptime(timeStamp,"%d.%m.%Y %H:%M:%S") )\
				.filter( "state_archived =", "0" )\
				.filter( "state_send = ", "1" )\
				.filter( "state_payed =", "1" )\
				.filter( "state_canceled =", "0" ).cursor( cursor )
		gotAtLeastOne = False

		for order in query.fetch():
			gotAtLeastOne = True
			self.setArchived( order )

		newCursor = query.getCursor()

		if gotAtLeastOne and newCursor and newCursor.urlsafe()!=cursor:
			self.doArchiveActiveOrdersTask( timeStamp, newCursor.urlsafe() )

	@callDeferred
	def doArchiveCancelledOrdersTask(self, timeStamp, cursor):
		#Archive all canceled orders
		query = self.viewSkel().all()\
				.filter( "changedate <", datetime.strptime(timeStamp,"%d.%m.%Y %H:%M:%S") )\
				.filter( "state_archived =", "0" )\
				.filter( "state_canceled =", "1" ).cursor( cursor)
		gotAtLeastOne = False
		for order in query.fetch():
			gotAtLeastOne = True
			self.setArchived( order )
		newCursor = query.getCursor()
		if gotAtLeastOne and newCursor and newCursor.urlsafe()!=cursor:
			self.doArchiveCancelledOrdersTask( timeStamp, newCursor.urlsafe() )
