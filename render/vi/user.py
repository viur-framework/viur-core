from server.render.json.user import UserRender as user
from server import utils, errors, session
import json

class UserRender(user):

	def loginSucceeded(self, **kwargs):
		if kwargs.get("thirdPartyLogin", False):
			raise errors.Redirect("/vi")

		return super(UserRender, self).loginSucceeded(**kwargs)
