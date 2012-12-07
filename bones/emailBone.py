# -*- coding: utf-8 -*-
import server
from server.bones import stringBone
import re

class emailBone( stringBone ):
	type = "str.email"
	
	def canUse( self, value ):
		regex = re.compile("[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}")
		res = regex.findall( unicode(value).lower() )
		if len( res ) == 1:
			return None
		else:
			return server.translate("Invalid emailaddress")
