from server.render.json.user import UserRender as user
from server import utils, errors, session
import json
import logging
import string

class UserRender(user):

	def loginSucceeded(self, **kwargs):
		msg = kwargs.get("msg", "")
		msg = "".join([x for x in msg if x in string.digits+string.ascii_letters+"-"])

		raise errors.Redirect("/vi/s/main.html#"+msg)

		#return super(UserRender, self).loginSucceeded(**kwargs)
