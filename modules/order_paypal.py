from server import db, request, errors
import urllib
from server.config import conf
from google.appengine.api import urlfetch

class PayPal( object ):
	"""
	Provides payments via Paypal.
	By default the sandbox is used, to change this to productionmode,
	set the following vars in viur.conf:

	viur.conf["paypal"] = {	'USER' : '<your API username>',
						'PWD' : '<your API password>',
						'SIGNATURE' : '<your API signature>'
	}
	"""

	class PayPalHandler:
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
			self.returnurl = returnurl or "http://%s/order/pp_paypal/doPayPal" % host
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

	def __init__(self, orderHandler):
		super( PayPal, self ).__init__()
		self.orderHandler = orderHandler


	def startProcessing( self, step, orderID ):
		def setTokenTxn( key, token ):
			order = db.Get( key )
			if not order:
				return
			order["paypal_token"] = urllib.unquote(token)
			db.Put( order )
		paypal = PayPal.PayPalHandler()
		key = db.Key( orderID )
		order = db.Get( key )
		if not order:
			return
		token = paypal.SetExpressCheckout( "%.2f" % order["price"] )
		db.RunInTransaction( setTokenTxn, key, token )
		raise( errors.Redirect( paypal.getPayURL( token ) ) )


	def doPayPal( self, token, PayerID,  *args, **kwargs ):
		order = db.Query( self.orderHandler.viewSkel().kindName ).filter( "paypal_token =", token).get()
		if not order:
			return("NO SUCH ORDER - PAYMENT ABORTED")
		paypal = PayPal.PayPalHandler()
		res = paypal.DoExpressCheckoutPayment( token, PayerID, "%.2f" % float(order["price"]) )
		if res["ACK"].lower()==u"success":
			self.orderHandler.setPayed( str( order.key() ) )
			return self.orderHandler.render.getEnv().get_template( self.orderHandler.render.getTemplateFileName("paypal_okay") ).render()
		else:
			return self.orderHandler.render.getEnv().get_template( self.orderHandler.render.getTemplateFileName("paypal_failed") ).render()
	doPayPal.exposed=True
