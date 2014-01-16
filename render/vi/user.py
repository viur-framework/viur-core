from server.render.json.user import UserRender as user
from server import errors

class UserRender( user ):
	def loginSucceeded( self,  **kwargs ):
		return("OKAY")
		#raise errors.Redirect("/vi")

	def logoutSuccess(self, **kwargs ):
		raise errors.Redirect("/vi/s/logout.html")

	def login( self, skel, **kwargs ):
		raise errors.Redirect("/vi/s/login.html")
