from server.render.json.user import UserRender as user
from server import utils
from server import errors

class UserRender( user ):
	def loginSucceeded( self,  **kwargs ):
		#Fixme: We need a better method for this..
		isGoogle=False
		if self.parent:
			try:
				if self.parent.getAuthMethod()=="X-GOOGLE-ACCOUNT":
					isGoogle=True
			except:
				pass
		if isGoogle:
			raise errors.Redirect("/vi")
		else:
			user=utils.getCurrentUser()
			if user and ("admin" in user["access"] or "root" in user["access"]):
				raise errors.Redirect("/vi/s/admin.html")
			else:
				raise errors.Redirect("/vi/s/nopermission.html")

	def logoutSuccess(self, **kwargs ):
		raise errors.Redirect("/vi/s/logout.html")

	def login( self, skel, **kwargs ):
		raise errors.Redirect("/vi/s/login.html")
