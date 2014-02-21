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