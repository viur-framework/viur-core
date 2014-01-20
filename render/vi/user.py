from server.render.json.user import UserRender as user
from server import errors

class UserRender( user ):
	def loginSucceeded( self,  **kwargs ):
		#Fixme: We need a better method for this..
		if self.parent:
			try:
				if self.parent.getAuthMethod()=="X-GOOGLE-ACCOUNT":
					raise errors.Redirect("/vi")
			except:
				pass
		return("OKAY")
		#raise errors.Redirect("/vi")

	def logoutSuccess(self, **kwargs ):
		raise errors.Redirect("/vi/s/logout.html")

	def login( self, skel, **kwargs ):
		raise errors.Redirect("/vi/s/login.html")
