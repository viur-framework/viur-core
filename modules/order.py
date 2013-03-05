# -*- coding: utf-8 -*-
import server
from server.applications.list import List
from server.skeleton import Skeleton
from server.bones import *
from server import errors, session, conf, request
from server.utils import validateSecurityKey
from server.tasks import callDefered
from server import db, request
import urllib
import hashlib
from google.appengine.api import urlfetch
import logging
import re
from server import request
from datetime import datetime, timedelta
from server.tasks import PeriodicTask

"""
class PaymentProviderGoogleCheckout( object ):
	"FIXME: CURRENTLY BROKEN "
	
	class GcController( gchecky.controller.Controller ):
		def handle_new_order(self, message, order_id, context, order=None):
			logging.debug( "Got a new GC Order")
			logging.debug( message )
			logging.error( order_id )
			logging.error( context )
			self.charge_order( order_id, 0.3 )
			return gchecky.model.ok_t()
		
		def handle_order_state_change(self, message, order_id, context, order=None):
			logging.debug( "GoogleCheckout order state change!")
			logging.debug( "Order %s changed its status to %s" % ( order_id, message.new_financial_order_state ) )
			if message.new_financial_order_state=="CHARGED":
				logging.error("FIXME")
			return gchecky.model.ok_t()
		
		def handle_risk_information(self, message, order_id, context, order=None):
			logging.debug( "GC Order RISK INFO")
			logging.debug( message )
			logging.error( order_id )
			logging.error( context )
			return gchecky.model.ok_t()
		
	
	def __init__(self, *args, **kwargs ):
		super( PaymentProviderGoogleCheckout, self ).__init__( *args, **kwargs )
		self._gcController = None
	
	def getGcController( self ):
		if not self._gcController:
			self._gcController = PaymentProviderGoogleCheckout.GcController(	vendor_id = conf["googleCheckout"]["merchantID"], 
																	merchant_key = conf["googleCheckout"]["merchantKey"], 
																	is_sandbox = conf["googleCheckout"]["isSandbox"], 
																	currency = conf["googleCheckout"]["currency"] )
		return( self._gcController )
	
	def paymentProvider_googlecheckout(self, step, orderID ):
		paypal = PaymentProviderPayPal.PayPal()
		order = ndb.Key( urlsafe = orderID ).get()
		if not order:
			assert False
			return
		cart =  gchecky.model.checkout_shopping_cart_t(
			shopping_cart =  gchecky.model.shopping_cart_t(
				items = [ gchecky.model.item_t(
						name = 'Apple',
						description = 'A Golden Apple for You, my dear',
						unit_price =  gchecky.model.price_t(
							value=0.15,
							currency = "GBP"
						),
					quantity = 2
					)
				]
			),
			checkout_flow_support =  gchecky.model.checkout_flow_support_t(	), 
			merchant_private_data = orderID
		)
		html_cart = self.getGcController().prepare_order(cart, order_id=orderID)
		raise Order.ReturnHtml( html_cart.html() )

	def doGC(self, *args, **kwargs ):
		return( self.getGcController().receive_xml( request.current.get().request.body ) )
	doGC.exposed = True

"""
class PaymentProviderPayPal:
	"""
	Provides payments via Paypal.
	By default the sandbox is used, to change this to productionmode,
	set the following vars in viur.conf:
	
	viur.conf["paypal"] = {	'USER' : '<your API username>', 
						'PWD' : '<your API password>', 
						'SIGNATURE' : '<your API signature>'
	}
	"""
	
	class PayPal:
		""" #PayPal utility class"""
		# by Mike Atlas, September 2007
		# No License Expressed. Feel free to distribute, modify, 
		# and use in any open or closed source project without credit to the author
		
		# Adapted for viur, Aug 2011

		signature_values = {}
		API_ENDPOINT = ""
		PAYPAL_URL = ""
		
		def __init__(self, currency=u"EUR", returnurl=None, cancelurl=None):
			if not "paypal" in conf.keys():
				self.signature_values = { #Set Sandbox-Credentials
					'USER' : 'sdk-three_api1.sdk.com', 
					'PWD' : 'QFZCWN5HZM8VBG7Q', 
					'SIGNATURE' : 'A-IzJhZZjhg29XQ2qnhapuwxIDzyAZQ92FRP5dqBzVesOkzbdUONzmOU', 
					'VERSION' : '3.0',
				}
				self.API_ENDPOINT = 'https://api-3t.sandbox.paypal.com/nvp' # Sandbox URL, not production
				self.PAYPAL_URL = 'https://www.sandbox.paypal.com/webscr&cmd=_express-checkout&token=' # Sandbox URL, not production
				self.signature = urllib.urlencode(self.signature_values) + "&"
			else:
				self.signature_values = {'VERSION' : '3.0' }
				self.signature_values.update( conf["paypal"] )
				self.API_ENDPOINT = 'https://api-3t.paypal.com/nvp' # Production !
				self.PAYPAL_URL = 'https://www.paypal.com/webscr&cmd=_express-checkout&token=' # Production !
				self.signature = urllib.urlencode(self.signature_values) + "&"
			url = request.current.get().request.url
			host = url[ url.find("://")+3: url.find("/", url.find("://")+5) ]
			self.returnurl = returnurl or "http://%s/order/doPayPal" % host
			self.cancelurl = cancelurl or "http://%s/site/paypal_failed" % host
			self.currency = currency
		
		def getPayURL(self, token):
			if self.API_ENDPOINT != 'https://api-3t.paypal.com/nvp': #Sandbox
				return "https://www.sandbox.paypal.com/webscr?cmd=_express-checkout&token=%s&RETURNURL=%s&CANCELURL=%s" % ( token, urllib.quote_plus( self.returnurl ), urllib.quote_plus( self.cancelurl ) )
			else: # Live System!
				return "https://www.paypal.com/webscr?cmd=_express-checkout&token=%s&RETURNURL=%s&CANCELURL=%s" % ( token, urllib.quote_plus( self.returnurl ), urllib.quote_plus( self.cancelurl ) )

		# API METHODS
		def SetExpressCheckout(self, amount):
			params = {
				'METHOD' : "SetExpressCheckout",
				'NOSHIPPING' : 1,
				'PAYMENTACTION' : 'Authorization',
				'RETURNURL' : self.returnurl, 
				'CANCELURL' : self.cancelurl, 
				'AMT' : amount,
				'CURRENCYCODE': self.currency
			}
			params_string = self.signature + urllib.urlencode(params)
			response = urlfetch.fetch(self.API_ENDPOINT, params_string.encode("UTF-8"),"POST",deadline=10).content.decode("UTF-8")
			response_token = ""
			for token in response.split('&'):
				if token.find("TOKEN=") != -1:
					response_token = token[ (token.find("TOKEN=")+6):]
			return response_token
		
		def GetExpressCheckoutDetails(self, token):
			params = {
				'METHOD' : "GetExpressCheckoutDetails",
				'RETURNURL' : self.returnurl, 
				'CANCELURL' : self.cancelurl, 
				'TOKEN' : token,
			}
			params_string = self.signature + urllib.urlencode(params)
			response = urllib.urlopen(self.API_ENDPOINT, params_string.encode("UTF-8")).read().decode("UTF-8")
			response_tokens = {}
			for token in response.split('&'):
				response_tokens[token.split("=u")[0]] = token.split("=u")[1]
			return response_tokens
		
		def DoExpressCheckoutPayment(self, token, payer_id, amt):
			params = {
				'METHOD' : "DoExpressCheckoutPayment",
				'PAYMENTACTION' : 'Sale',
				'RETURNURL' : self.returnurl, 
				'CANCELURL' : self.cancelurl, 
				'TOKEN' : token,
				'AMT' : amt,
				'PAYERID' : payer_id,
				'CURRENCYCODE': self.currency, 
			}
			params_string = self.signature + urllib.urlencode(params)
			response = urlfetch.fetch(self.API_ENDPOINT, params_string.encode("UTF-8"),"POST",deadline=10).content.decode("UTF-8")
			response_tokens = {}
			for token in response.split('&'):
				response_tokens[token.split("=")[0]] = token.split("=")[1]
			for key in list(response_tokens.keys()):
					response_tokens[key] = urllib.unquote(response_tokens[key])
			return response_tokens
			
		def GetTransactionDetails(self, tx_id):
			params = {
				'METHOD' : "GetTransactionDetails", 
				'TRANSACTIONID' : tx_id,
			}
			params_string = self.signature + urllib.urlencode(params)
			response = urllib.urlopen(self.API_ENDPOINT, params_string.encode("UTF-8")).read().decode("UTF-8")
			response_tokens = {}
			for token in response.split('&'):
				response_tokens[token.split("=u")[0]] = token.split("=u")[1]
			for key in list(response_tokens.keys()):
					response_tokens[key] = urllib.unquote(response_tokens[key])
			return response_tokens
	
	
	def paymentProvider_paypal( self, step, orderID ):
		paypal = PaymentProviderPayPal.PayPal()
		order = db.Get( db.Key( orderID ) )
		if not order:
			return
		token = paypal.SetExpressCheckout( "%.2f" % order["price"] )
		order["paypal_token"] = urllib.unquote(token)
		db.Put( order )
		raise( errors.Redirect( paypal.getPayURL( token ) ) )
		
	
	def doPayPal( self, token, PayerID,  *args, **kwargs ):
		order = db.Query( self.kindName ).filter( "paypal_token =", token).get()
		if not order:
			return("NO SUCH ORDER - PAYMENT ABORTED")
		paypal = PaymentProviderPayPal.PayPal()
		res = paypal.DoExpressCheckoutPayment( token, PayerID, "%.2f" % float(order["price"]) )
		if res["ACK"].lower()==u"success":
			self.setPayed( str( order.key() ) )
			return self.render.getEnv().get_template( self.render.getTemplateFileName("paypal_okay") ).render()
		else:
			return self.render.getEnv().get_template( self.render.getTemplateFileName("paypal_failed") ).render()
	doPayPal.exposed=True

class PaymentProviderSofort:
	"""
	Provides payments via Sofort.com (SOFORT-Classic).
	You must set the following variables before using this:
	viur.conf["sofort"] = {	"userid":"<your userid>",
						"projectid":"<project-id>",
						"projectpassword":"<project-password>",
						"notificationpassword":"<notificationpassword>" 
						}
	"""

	def getSofortURL(self, orderID ):
		order = db.Get( db.Key( orderID ) )
		hashstr = "%s|%s|||||%.2f|EUR|%s||%s||||||%s" % (conf["sofort"]["userid"], conf["sofort"]["projectid"], float( order["price"] ), str(order.key()), str(order.key()), conf["sofort"]["projectpassword"] )
		hash = hashlib.sha512(hashstr.encode("UTF-8")).hexdigest()
		returnURL = "https://www.sofortueberweisung.de/payment/start?user_id=%s&project_id=%s&amount=%.2f&currency_id=EUR&reason_1=%s&user_variable_0=%s&hash=%s" % ( conf["sofort"]["userid"], conf["sofort"]["projectid"], float( order["price"]) , str(order.key()), str(order.key()), hash)
		return( returnURL )

	def paymentProvider_sofort(self, step, orderID ):
		raise errors.Redirect( self.getSofortURL( orderID ) )

	def sofortStatus(self, *args, **kwargs):
		sortOrder = [	"transaction","user_id","project_id",
			"sender_holder", "sender_account_number", "sender_bank_code",
			"sender_bank_name", "sender_bank_bic", "sender_iban",
			"sender_country_id", "recipient_holder", "recipient_account_number",
			"recipient_bank_code", "recipient_bank_name", "recipient_bank_bic",
			"recipient_iban", "recipient_country_id", "international_transaction",
			"amount", "currency_id", "reason_1", "reason_2", "security_criteria",
			"user_variable_0", "user_variable_1","user_variable_2", "user_variable_3",
			"user_variable_4", "user_variable_5", "created"]
		hashstr = "|".join( [ kwargs[key] for key in sortOrder ]+[conf["sofort"]["notificationpassword"]] )
		if hashlib.sha512(hashstr.encode("utf-8")).hexdigest()!=kwargs["hash"]:
			logging.error("RECIVED INVALID HASH FOR sofort (%s!=%s)" % ( hashlib.sha512(hashstr.encode("utf-8")).hexdigest(),kwargs["hash"] ) )
			return("INVALID HASH")
		order = db.Get( db.Key( kwargs["user_variable_0"] ) )
		if not order:
			logging.error("RECIVED UNKNOWN ORDER by sofort (%s)" % ( kwargs["user_variable_0"] ) )
			return("UNKNOWN ORDER")
		if ("%.2f" % order["price"]) != kwargs["amount"]:
			logging.error("RECIVED INVALID AMOUNT PAYED sofort (%s!=%s)" % ( order["price"], kwargs["amount"] ) )
			return("INVALID AMOUNT")
		self.setPayed( kwargs["user_variable_0"] )
		return("OKAY")
	sofortStatus.exposed=True
	
	def doSofort(self, *args, **kwargs ):
		return self.render.getEnv().get_template( self.render.getTemplateFileName("sofort_okay") ).render()
	doSofort.exposed=True

	def sofortFailed(self, *args, **kwargs ):
		return self.render.getEnv().get_template( self.render.getTemplateFileName("sofort_failed") ).render()
	sofortFailed.exposed=True


class Order( List ):
	"""
	Provides an unified orderingprocess with payment-handling.
	This is encoded as a state machine.
	"""

	archiveDelay = timedelta( days=31 ) # Archive completed orders after 31 Days
	kindName = "order"
	states = [	"complete", # The user completed all steps of the process, he might got redirected to a paymentprovider
				"payed", #This oder has been payed
				"rts", #Ready to Ship 
				"send", # Goods got shipped
				"canceled",  # Order got canceled
				"archived"  #This order has been executed
				]
	
	class SkipStep( Exception ):
		"""Raise this Exception to skip the current step"""
		pass

	class ReturnHtml( Exception ):
		"""Raise this Exception to force the return of the given HTML inside a pre/post handler"""
		def __init__(self, html ):
			super( Order.ReturnHtml, self ).__init__()
			self.html = html
		
	adminInfo = {
		"name": "Orders", #Name of this modul, as shown in Apex (will be translated at runtime)
		"handler": "list.order",  #Which handler to invoke
		"icon": "icons/modules/cart.png", #Icon for this modul
		"filter":{"orderby":"creationdate","orderdir":1,"state_complete":"1" }, 
		"columns":["idx","bill_firstname","bill_lastname","amt","price","creationdate"],
		"views" : [	{ "name": u"Not shipped", "filter":{"state_archived": "0",  "state_complete":"1", "state_send":"0", "state_canceled":"0", "orderby":"creationdate","orderdir":1 }, "icon":"icons/status/unsend.png", "columns":["idx","bill_firstname","bill_lastname","amt","price","creationdate"]},
					{ "name": u"Unpaid", "filter":{"state_archived": "0", "state_complete":"1", "state_payed":"0","state_canceled":"0", "orderby":"creationdate","orderdir":1}, "icon":"icons/status/unpayed.png", "columns":["idx","bill_firstname","bill_lastname","amt","price","creationdate"] },
					{ "name": u"Paid","filter":{"state_archived": "0", "state_complete":"1", "state_payed":"1", "state_canceled":"0", "orderby":"creationdate","orderdir":1}, "icon":"icons/status/payed.png", "columns":["idx","bill_firstname","bill_lastname","amt","price","creationdate"] },
					{ "name": u"Shipped", "filter":{"state_archived": "0", "state_complete":"1", "state_canceled":"0", "state_send":"1","orderby":"changedate","orderdir":1}, "icon":"icons/status/send.png", "columns":["idx","bill_firstname","bill_lastname","amt","price","creationdate"] }, 
					{ "name": u"Ready to ship", "filter":{"state_archived": "0","state_canceled":"0",  "state_complete":"1", "state_send":"0","state_rts":"1","orderby":"changedate","orderdir":1}, "icon":"icons/status/send.png", "columns":["idx","bill_firstname","bill_lastname","amt","price","creationdate"] }, 
					{ "name": u"Canceled", "filter":{"state_archived": "0", "state_canceled":"1", "state_complete":"1",  "orderby":"changedate","orderdir":1}, "icon":"icons/status/send.png", "columns":["idx","bill_firstname","bill_lastname","amt","price","creationdate"] }, 
					{ "name": u"Archived", "filter":{"state_archived": "1", "state_complete":"1", "orderby":"changedate","orderdir":1}, "icon":"icons/status/send.png", "columns":["idx","bill_firstname","bill_lastname","amt","price","creationdate"] }
			]
		}

	class billAddressSkel( Skeleton ):
		kindName = "order"
		bill_gender = selectOneBone( descr=u"Gender", required=True, values={"male":"Mr.", "female":"Mrs."} )
		bill_firstname = stringBone( descr=u"First name", params={"indexed": True, "frontend_list_visible": True},required=True,unsharp=True )
		bill_lastname = stringBone( descr=u"Last name", params={"indexed": True, "frontend_list_visible": True},required=True,unsharp=True )
		bill_street = stringBone( descr=u"Street", params={"indexed": True, "frontend_list_visible": True},required=True )
		bill_zip = stringBone( descr=u"Zipcode",required=True,unsharp=True )
		bill_city = stringBone( descr=u"City",required=True )
		bill_country = selectCountryBone(descr=u"Country", required=True, codes=selectCountryBone.ISO2, defaultValue=u"de" )
		bill_email = emailBone( descr=u"Email", required=True, unsharp=True )
		useshippingaddress = booleanBone( descr=u"Use alternative Shipment-Address", required=True)

	class shippingAddressSkel( Skeleton ):
		kindName = "order"
		extrashippingaddress = selectOneBone( descr=u"special shippingaddress", values={"0":"No","1":"Yes"}, required=True, defaultValue=u"0", visible=False )
		shipping_firstname = stringBone( descr=u"First name", params={"indexed": True, "frontend_list_visible": True},required=True,unsharp=True )
		shipping_lastname = stringBone( descr=u"Last name", params={"indexed": True, "frontend_list_visible": True},required=True,unsharp=True )
		shipping_street = stringBone( descr=u"Street", params={"indexed": True, "frontend_list_visible": True},required=True )
		shipping_zip = stringBone( descr=u"Zipcode",required=True,unsharp=True )
		shipping_city = stringBone( descr=u"City",required=True )
		shipping_country = selectCountryBone(descr=u"Country", required=True, codes=selectCountryBone.ISO2, defaultValue=u"de" )

	class shipTypePayment( Skeleton ):
		kindName = "order"
		shipping_type = selectOneBone( descr=u"Type of shipment", values={"0":"uninsured", "1":"insured"} , required=True)
		payment_type  = selectOneBone( descr=u"Type of payment", values={"prepaid":"Bank-transfer", "pod":"Pay on Deliver", "paypal":"Paypal", "sofort":"Sofort"} , required=True)

	class listSkel( Skeleton ):
		kindName = "order"
		bill_gender = selectOneBone( descr=u"Bill-gender", required=True, values={"male":"Mr.", "female":"Mrs."} )
		bill_firstname = stringBone( descr=u"Bill-first name", params={"indexed": True, "frontend_list_visible": True},required=True,unsharp=True )
		bill_lastname = stringBone( descr=u"Bill-last name", params={"indexed": True, "frontend_list_visible": True},required=True,unsharp=True )
		bill_street = stringBone( descr=u"Bill-street", params={"indexed": True, "frontend_list_visible": True},required=True )
		bill_city = stringBone( descr=u"Bill-city",required=True )
		bill_zip = stringBone( descr=u"Bill-zipcode",required=True,unsharp=True )
		bill_country = selectCountryBone( descr=u"Bill-country", codes=selectCountryBone.ISO2, required=True)
		bill_email = stringBone( descr=u"email", required=True, unsharp=True)
		shipping_firstname = stringBone( descr=u"Shipping-first name", params={"indexed": True, "frontend_list_visible": True},required=True,unsharp=True )
		shipping_lastname = stringBone( descr=u"Shipping-last name", params={"indexed": True, "frontend_list_visible": True},required=True,unsharp=True )
		shipping_street = stringBone( descr=u"Shipping-street", params={"indexed": True, "frontend_list_visible": True},required=True )
		shipping_city = stringBone( descr=u"Shipping-city",required=True )
		shipping_zip = stringBone( descr=u"Shipping-zipcode",required=True,unsharp=True )
		shipping_country = selectCountryBone( descr=u"Shipping-country", codes=selectCountryBone.ISO2, required=True )
		price = numericBone( descr=u"Price", mode=u"float", required=True, readOnly=True )
		payment_type = selectOneBone( descr=u"type of payment", values = {"prepaid":"Bank-transfer", "pod":"Pay on Delivery", "paypal":"Paypal", "sofort":"Sofort"}, required=False, visible=False )
		state_complete = selectOneBone( descr=u"Complete", values={"0":"No","1":"Yes"}, defaultValue=0, readOnly=True, required=True, visible=False )
		state_payed = selectOneBone( descr=u"Paid", values={"0":"No","1":"Yes"}, defaultValue=0, readOnly=True, required=True, visible=False )
		state_send = selectOneBone( descr=u"Send", values={"0":"No","1":"Yes"}, defaultValue=0, readOnly=True, required=True, visible=False )
		state_rts = selectOneBone( descr=u"Ready to ship", values={"0":"No","1":"Yes"}, defaultValue=0, readOnly=True, required=True, visible=False )
		state_canceled = selectOneBone( descr=u"Canceled", values={"0":"No","1":"Yes"}, defaultValue=0, readOnly=True, required=True, visible=False )
		state_archived = selectOneBone( descr=u"Archived", values={"0":"No","1":"Yes"}, defaultValue=0, readOnly=True, required=True, visible=False )
		idx = numericBone( descr=u"Order-number", required=True, readOnly=True, params={"indexed": True, "frontend_list_visible": True} )
	viewSkel = listSkel

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
		if not dbObj:
			return( [] )
		res = []
		for state in self.states:
			stateName = "state_%s" % state
			if stateName in dbObj.keys() and str( dbObj[ stateName ] )=="1":
				res.append( state )
		return( res )

	
	def setComplete( self, orderID ):
		"""
		Marks an order as Complete
		May be overriden to hook this event
		
		@type orderID: string
		@param orderID: ID to mark completed
		"""
		order = Order.listSkel()
		if not order.fromDB( str(orderID) ):
			return( False )
		self.setState( orderID, "complete")
		if order.payment_type.value == "pod":
			states = self.getStates( orderID )
			if not any( [ x in states for x in ["canceled", "rts", "send"] ] ):
				self.setRTS( orderID )
		self.assignBillSequence( str(orderID) )
		return( True )

	def setRTS(self, orderID):
		"""
			Marks an order ready to send
			May be overriden to hook this event
			
			@type orderID: string
			@param orderID: ID to mark
		"""
		self.setState( orderID, "rts")


	def setPayed(self, orderID):
		"""
		Marks an order as Payed
		May be overriden to hook this event

		@type orderID: string
		@param orderID: ID to mark completed
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
		May be overriden to hook this event

		@type orderID: string
		@param orderID: ID to mark completed
		"""
		self.setState( orderID, "send" )
		self.setState( orderID, "rts", True )
		self.sendOrderShippedEMail( orderID )
		return( True )

	def setCanceled(self, orderID):
		"""
		Marks an order as Canceled
		May be overriden to hook this event

		@type orderID: string
		@param orderID: ID to mark completed
		"""
		self.setState( orderID, "canceled" )
		self.setState( orderID, "rts", True )
		self.sendOrderCanceledEMail( orderID )
		return( True )
	
	def setArchived(self, orderID ):
		"""
		Marks an order as Archived
		May be overriden to hook this event

		@type orderID: string
		@param orderID: ID to mark completed
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

	def markPayed( self, id, skey ):
		if not self.canEdit( id ):
			raise errors.Unauthorized()
		if not validateSecurityKey( skey ):
			raise errors.PreconditionFailed()
		self.setPayed( id )
		return("OKAY")
	markPayed.exposed = True

	def markSend( self, id, skey ):
		if not self.canEdit( id ):
			raise errors.Unauthorized()
		if not validateSecurityKey( skey ):
			raise errors.PreconditionFailed()
		self.setSend( id )
		return("OKAY")
	markSend.exposed = True
	
	def markCanceled( self, id, skey ):
		if not self.canEdit( id ):
			raise errors.Unauthorized()
		if not validateSecurityKey( skey ):
			raise errors.PreconditionFailed()
		self.setCanceled( id )
		return("OKAY")
	markCanceled.exposed = True


	def checkSkipShippingAddress( self, step, orderID, *args, **kwargs ):
		"""
		This step updates the current order copys the values from 
		billAddressSkel to shippingAddressSkel if extrashippingaddress is False
		
		@type step: Int
		@param step: Current step within the ordering process
		@type orderID: string
		@param orderID: ID to mark completed
		"""
		billSkel = Order.billAddressSkel()
		billSkel.fromDB( orderID )
		if str(billSkel.useshippingaddress.value)==u"0":
			shippingSkel = Order.shippingAddressSkel()
			keyMap = { 	"bill_firstname": "shipping_firstname", 
						"bill_lastname" : "shipping_lastname", 
						"bill_street": "shipping_street", 
						"bill_city": "shipping_city", 
						"bill_zip": "shipping_zip", 
						"bill_country": "shipping_country" }
			for srcKey, destKey in keyMap.items():
				getattr( shippingSkel, destKey ).value = getattr( billSkel, srcKey ).value
			shippingSkel.toDB( orderID )
			raise Order.SkipStep()

	def calcualteOrderSum( self, step, orderID, *args, **kwargs ):
		"""
		Calculates the final price for this order.
		*Must* be called before any attempt is made to start a payment process
		
		@type step: Int
		@param step: Current step within the ordering process
		@type orderID: string
		@param orderID: ID to calculate the price for
		"""
		price = sum( [x[3] for x in self.getBillItems( orderID ) ] )
		orderObj = db.Get( db.Key( str( orderID ) ) )
		orderObj["price"] = price
		db.Put( orderObj )

	
	def startPayment( self, step, orderID, *args, **kwargs ):
		"""
		Starts paymentprocessing for this order.
		The order is marked completed, so no further changes can be made.
		
		@type step: Int
		@param step: Current step within the ordering process
		@type orderID: string
		@param orderID: ID to mark completed
		"""
		order = Order.listSkel()
		order.fromDB( orderID )
		if not str(order.state_complete.value)=="1":
			session.current["order_"+self.kindName] = None
			session.current.markChanged() #Fixme
			self.setComplete( orderID )
			if "paymentProvider_%s" % order.payment_type.value in dir( self ):
				getattr( self, "paymentProvider_%s" % order.payment_type.value )( step, orderID )
	
	def paymentProvider_pod( self, step, orderID ):
		"""
			If Pay-On-Delivery is choosen, immediately mark this order as ready to ship
		"""
		self.setRTS( orderID )

	def getBillItems(self, orderID ):
		"""
		Returns all Items for the given Order.
		Must be overriden.

		@type orderID: string
		@param orderID: ID to mark completed
		@return: [ ( Int Amount, Unicode Description , Float Price of one Item, Float Price of all Items (normaly Price of one Item*Amount), Float Included Tax )  ] 
		"""

		return( [] )
	getBillItems.internalExposed = True
	
	def billSequenceAvailable( self, orderID ):
		self.sendOrderCompleteEMail( orderID )
	
	
	@callDefered
	def assignBillSequence( self, orderID ):
		"""Assigns an unique order-ID to the given Order """

		def  getIDtxn( kindName, orderID ):
			"""Generates and returns a new, unique ID"""
			seqObj = db.GetOrInsert( kindName," viur_bill_sequences", count=1000)
			idx = seqObj["count"]
			seqObj["count"] += 1
			db.Put( seqObj )
			return( str(idx) )

		def setIDtxn( orderID, idx ):
			"""Assigns the new orderID to the given order"""
			dbObj = db.Get( db.Key( orderID ) )
			if not dbObj:
				return
			dbObj[ "idx" ] = idx
			db.Put( dbObj )
		dbObj = db.Get( db.Key( orderID ) )
		if not dbObj:
			return
		idx = db.RunInTransaction( getIDtxn, self.kindName, orderID )
		db.RunInTransaction( setIDtxn, orderID, idx  )
		self.billSequenceAvailable( orderID )
		
		
	steps = 	[	
				{	
					"mainHandler": {
						"action": "edit", 
						"skeleton": billAddressSkel, 
						"template": "order_billaddress", 
						"descr":u"Billinginformation"
					}
				}, 
				{	
					"preHandler": checkSkipShippingAddress, 
					"mainHandler": {
						"action": "edit", 
						"skeleton": shippingAddressSkel, 
						"template": "order_shipaddress", 
						"descr":u"Shippinginformation"
					}
				}, 
				{	
					"mainHandler": {
						"action": "edit", 
						"skeleton": shipTypePayment, 
						"template": "order_payment", 
						"descr":u"Payment"
					}, 
					"postHandler": calcualteOrderSum
				}, 
				{	
					"mainHandler": {
						"action": "view", 
						"skeleton": listSkel, 
						"template": "order_verify", 
						"descr":u"Overview"
					}
				}, 
				{	
					"preHandler": startPayment, 
					"mainHandler": {
						"action": "view", 
						"skeleton": listSkel, 
						"template": "order_complete",
						"descr":u"Order completed"
					}
				}
			]
	
	
	
	editSkel = listSkel
	addSkel = listSkel
	
	def getSteps(self):
		thesteps = []
		for step in self.steps[:]:
			step = step.copy()
			step["mainHandler"] = step["mainHandler"].copy()
			if step["mainHandler"]["descr"]:
				step["mainHandler"].update({"descr": _(step["mainHandler"]["descr"])})
			thesteps.append( step )
		return (thesteps)
	getSteps.internalExposed=True
	
	def getBillPdf(self, orderID):
		"""
			Should be overriden to return the Bill (as pdf) for the given order.
			
			@param orderID: Order, for which the the bill should be generated.
			@type orderID: String
			@returns: Bytes or None
		"""
		return( None )

	def getDeliveryNotePdf(self, orderID ):
		"""
			Should be overriden to return the delivery note (as pdf) for the given order.
			
			@param orderID: Order, for which the the bill of delivery should be generated.
			@type orderID: String
			@returns: Bytes or None
		"""
		return( None )
	
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
	getBill.exposed=True

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
	getDeliveryNote.exposed=True
	
	def checkout( self, step=None, id=None, skey=None, *args, **kwargs ):
		if( step==None ):
			logging.info("Starting new checkout process")
			billObj = db.Entity( self.kindName )
			billObj["idx"] = "0000000";
			for state in self.states:
				billObj[ "state_%s" % state ] = "0"
			db.Put( billObj )
			id = str( billObj.key() )
			#Try copying the Cart
			if "amountSkel" in dir ( self ):
				cart = session.current.get("cart_products") or {}
				s = self.amountSkel()
				products = []
				for prod, amt in cart.items():
					for i in range(0,amt):
						products.append( str(prod) )
				s.fromClient( {"product": products} )
				s.toDB( id )
			session.current["order_"+self.kindName] = {"id": str( id ), "completedSteps": [] }
			session.current.markChanged()
			raise errors.Redirect("?step=0&id=%s" % str( id ) )
		elif id:
			try:
				orderID = db.Key( id )
				step = int( step )
				assert( step>=0 )
				assert( step < len( self.steps ) )
			except:
				raise errors.NotAcceptable()
			sessionInfo = session.current.get("order_"+self.kindName)
			if not sessionInfo or not sessionInfo.get("id") == str( orderID ):
				raise errors.Unauthorized()
			if step in sessionInfo["completedSteps"]:
				session.current["order_"+self.kindName]["completedSteps"] = [ x for x in sessionInfo["completedSteps"] if x<step ]
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
						currentStep["preHandler"]( self, step, str(orderID), *args, **kwargs )
				except Order.SkipStep:
					session.current["order_"+self.kindName]["completedSteps"].append( step )
					session.current.markChanged()
					raise errors.Redirect("?step=%s&id=%s" % (str( step+1 ), str( str(orderID) ) ) )
				except Order.ReturnHtml as e:
					return( e.html )
			if "requiresSecutityKey" in currentStep.keys() and currentStep["requiresSecutityKey"] :
				validateSecurityKey()
				pass
			if "mainHandler" in currentStep.keys():
				if currentStep["mainHandler"]["action"] == "edit":
					skel = currentStep["mainHandler"]["skeleton"]()
					skel.fromDB( str( orderID ) )
					if not len( kwargs.keys() ) or not skel.fromClient( kwargs ):
						return( self.render.edit( skel, tpl=currentStep["mainHandler"]["template"], step=step ) )
					skel.toDB( str( orderID ) )
				if currentStep["mainHandler"]["action"] == "view":
					if not "complete" in kwargs or not kwargs["complete"]==u"1":
						skel = currentStep["mainHandler"]["skeleton"]()
						skel.fromDB( str( orderID ) )
						return( self.render.view( skel, tpl=currentStep["mainHandler"]["template"], step=step ) )
				elif currentStep["mainHandler"]["action"] == "function":
					res = currentStep["mainHandler"]["function"]( self, step, str(orderID), *args, **kwargs )
					if res:
						return( res )
			if "postHandler" in currentStep.keys():
				currentStep["postHandler"]( self, step, str(orderID), *args, **kwargs )
			session.current["order_"+self.kindName]["completedSteps"].append( step )
			session.current.markChanged()
			raise errors.Redirect("?step=%s&id=%s" % (str( step+1 ), str( orderID ) ) )
	checkout.exposed=True

	def archiveOrder(self, order ):
		self.setState( order.key.urlsafe(), "archived" )
		self.sendOrderArchivedEMail( order.key.urlsafe() )
		logging.error("Order archived: "+str( order.key.urlsafe() ) )

	@PeriodicTask(60*24)
	def archiveOrdersTask( self, *args, **kwargs ):
		logging.debug("Archiving old orders")
		#Archive all payed,send and not canceled orders
		orders = generateExpandoClass( self.viewSkel().kindName ).query()\
				.filter( ndb.GenericProperty("changedate") < (datetime.now()-self.archiveDelay) )\
				.filter( ndb.GenericProperty("state_archived") == "0" )\
				.filter( ndb.GenericProperty("state_send") == "1" )\
				.filter( ndb.GenericProperty("state_payed") == "1" )\
				.filter( ndb.GenericProperty("state_canceled") == "0" ).iter()
		for order in orders:
			self.setArchived( order )
		#Archive all canceled orders
		orders = generateExpandoClass( self.viewSkel().kindName ).query()\
				.filter( ndb.GenericProperty("changedate") < (datetime.now()-self.archiveDelay) )\
				.filter( ndb.GenericProperty("state_archived") == "0" )\
				.filter( ndb.GenericProperty("state_canceled") == "1" ).iter()
		for order in orders:
			self.setArchived( order )

	
order=Order
