# -*- coding: utf-8 -*-
from server import utils
from server.bones import stringBone
from hashlib import sha256
import hmac
from struct import Struct
from operator import xor
from itertools import starmap
from server.config import conf
import string, random


def pbkdf2(password, salt, iterations=1001, keylen=42):
	"""
		An implementation of PBKDF2 (http://wikipedia.org/wiki/PBKDF2)
		
		Mostly based on the implementation of 
		https://github.com/mitsuhiko/python-pbkdf2/blob/master/pbkdf2.py
		
		:copyright: (c) Copyright 2011 by Armin Ronacher.
		:license: BSD, see LICENSE for more details.
	"""
	_pack_int = Struct('>I').pack
	if isinstance(password, unicode):
		password = password.encode("UTF-8")
	if isinstance(salt, unicode):
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
			rv = starmap(xor, zip(rv, u))
		buf.extend(rv)
	return (''.join(map(chr, buf))[:keylen]).encode("hex")


class passwordBone(stringBone):
	"""
		A bone holding passwords.
		This is always empty if read from the database.
		If its saved, its ignored if its values is still empty.
		If its value is not empty, its hashed (with salt) and only the resulting hash 
		will be written to the database
	"""
	type = "password"
	saltLength = 13
	minPasswordLength = 8
	passwordTests = [
		lambda val: val.lower() != val,  # Do we have upper-case characters?
		lambda val: val.upper() != val,  # Do we have lower-case characters?
		lambda val: any([x in val for x in "0123456789"]),  # Do we have any digits?
		lambda val: any([x not in (string.ascii_lowercase + string.ascii_uppercase + string.digits) for x in val]),
		# Special characters?
	]
	passwordTestThreshold = 3

	def isInvalid(self, value):
		if not value:
			return False

		if len(value) < self.minPasswordLength:
			return _("The entered password is to short - it requires at least {{length}} characters.",
					 length=self.minPasswordLength)

		# Run our password test suite
		testResults = []
		for test in self.passwordTests:
			testResults.append(test(value))

		if sum(testResults) < self.passwordTestThreshold:
			return _("The entered password is too weak.")

		return False

	def fromClient(self, valuesCache, name, data):
		value = data.get(name)
		if not value:
			return "No value entered"

		err = self.isInvalid(value)
		if err:
			return err

		valuesCache[name] = value

	def serialize(self, valuesCache, name, entity):
		if valuesCache.get(name, None) and valuesCache[name] != "":
			salt = utils.generateRandomString(self.saltLength)
			passwd = pbkdf2(valuesCache[name][: conf["viur.maxPasswordLength"]], salt)
			entity.set(name, passwd, self.indexed)
			entity.set("%s_salt" % name, salt, self.indexed)

		return entity

	def unserialize(self, valuesCache, name, values):
		return {name: ""}
