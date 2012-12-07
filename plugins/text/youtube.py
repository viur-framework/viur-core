# -*- coding: utf-8 -*-
from server.skeleton import Skeleton
from server.bones import *


class YouTube():
	type = "block" #Block or inline Element?
	name= "youtube" #Unique Identifier
	descr ="Youtube-Video" #Translatable description
	
	class dataSkel( Skeleton ):
		vidid = stringBone( descr="Youtube ID", required=True ) #VideoID of the Movie
	
	@staticmethod
	def render( vidid=None, *args, **kwargs ):
		tpl = """<iframe class="YouTube-Frame" src="https://www.youtube.com/embed/%s" allowfullscreen>YouTube Video Link</iframe>"""
		if vidid:
			return( tpl % vidid )
		else:
			return("")

