# -*- coding: utf-8 -*-
from server.bones import stringBone
from hashlib import sha256
import hmac
from struct import Struct
from operator import xor
from itertools import izip, starmap
from server.config import conf
import string, random

def pbkdf2( password, salt, iterations=1001, keylen=42):
	"""
		An implementation of PBKDF2 (http://wikipedia.org/wiki/PBKDF2)
		
		Mostly based on the implementation of 
		https://github.com/mitsuhiko/python-pbkdf2/blob/master/pbkdf2.py
		
		:copyright: (c) Copyright 2011 by Armin Ronacher.
		:license: BSD, see LICENSE for more details.
	"""
	_pack_int = Struct('>I').pack
	if isinstance( password, unicode ):
		password = password.encode("UTF-8")
	if isinstance( salt, unicode ):
		salt = salt.encode("UTF-8")
	mac = hmac.new(password, None, sha256)
	def _pseudorandom(x, mac=mac):
		h = mac.copy()
		h.update(x)
		return map(ord, h.digest())
	buf = []
	for block in xrange(1, -(-keylen // mac.digest_size) + 1):
		rv = u = _pseudorandom(salt + _pack_int(block))
		for i in xrange(iterations - 1):
			u = _pseudorandom(''.join(map(chr, u)))
			rv = starmap(xor, izip(rv, u))
		buf.extend(rv)
	return (''.join(map(chr, buf))[:keylen]).encode("hex")

class passwordBone( stringBone ):
	"""
		A bone holding passwords.
		This is allways empty if read from the database.
		If its saved, its ignored if its values is still empty.
		If its value is not empty, its hashed (with salt) and only the resulting hash 
		will be written to the database
	"""
	type = "password"
	saltLenth = 13
	
	def serialize( self, name, entity ):
		if self.value and self.value != "":
			salt = ''.join( [ random.choice(string.ascii_lowercase+string.ascii_uppercase + string.digits) for x in range(self.saltLenth) ] )
			passwd = pbkdf2( self.value, salt )
			entity.set( name, passwd, self.indexed )
			entity.set( "%s_salt" % name, salt, self.indexed )
		return( entity )

	def unserialize( self, name, values ):
		return( {name: ""} )
