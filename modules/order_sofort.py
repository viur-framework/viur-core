

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
