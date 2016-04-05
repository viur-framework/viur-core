from server.render.json.user import UserRender as user
from server import utils, errors, session
import json

class UserRender(user):

	def loginSucceeded(self, **kwargs):
		if "thirdPartyLogin" in kwargs.keys() and kwargs["thirdPartyLogin"]:
			raise errors.Redirect("/vi")

		if session.current.get("_otp_user"):
			return json.dumps("OKAY:OTP")

		user = utils.getCurrentUser()
		if user and ("admin" in user["access"] or "root" in user["access"]):
			return json.dumps("OKAY")

		return json.dumps("OKAY:NOADMIN")
