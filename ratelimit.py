# -*- coding: utf-8 -*-
#from google.appengine.api import memcache
from viur.core import utils
from viur.core.utils import currentRequest
from datetime import datetime


class RateLimit(object):
	"""
		This class is used to restrict access to certain functions to *maxRate* calls per minute.

		Usage: Create an instance of this object in you modules __init__ function. then call
		isQuotaAvailable before executing the action to check if there is quota available and
		after executing the action decrementQuota.

	"""

	def __init__(self, resource, maxRate, minutes, method):
		"""
		Initializes a new RateLimit gate.
		:param resource: Name of the resource to protect
		:type resource: str
		:param maxRate: Amount of tries allowed in the give time-span
		:type maxRate: int
		:param minutes: Length of the time-span in minutes
		:type minutes: int
		:param method: Lock by IP or by the current user
		:type method: 'ip' | 'user'
		"""
		super(RateLimit, self).__init__()
		self.resource = resource
		self.maxRate = maxRate
		self.minutes = minutes
		self.steps = min(minutes, 5)
		self.secondsPerStep = 60 * (float(minutes) / float(self.steps))
		assert method in ["ip", "user"], "method must be 'ip' or 'user'"
		self.useUser = method == "user"

	def _getEndpointKey(self):
		"""
		:warning:
			It's invalid to call _getEndpointKey if method is set to user and there's no user logged in!

		:return: the key associated with the current endpoint (it's IP or the key of the current user)
		"""
		if self.useUser:
			user = utils.getCurrentUser()
			assert user, "Cannot decrement usage from guest!"
			return user["key"]
		else:
			remoteAddr = currentRequest.get().request.remote_addr
			if "::" in remoteAddr:  # IPv6 in shorted form
				remoteAddr = remoteAddr.split(":")
				blankIndex = remoteAddr.index("")
				missigParts = ["0000"] * (8 - len(remoteAddr))
				remoteAddr = remoteAddr[:blankIndex] + missigParts + remoteAddr[blankIndex + 1:]
				return ":".join(remoteAddr[:4])
			elif ":" in remoteAddr:  # It's IPv6, so we remove the last 64 bits (interface id)
				# as it is easily controlled by the user
				return ":".join(remoteAddr.split(":")[4:])
			else:  # It's IPv4, simply return that address
				return remoteAddr

	def _getCurrentTimeKey(self):
		"""
		:return: the current lockperiod used in second position of the memcache key
		"""
		dateTime = datetime.now()
		key = dateTime.strftime("%Y-%m-%d-%%s")
		secsinceMidnight = (dateTime - dateTime.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()
		currentStep = int(secsinceMidnight / self.secondsPerStep)
		return key % currentStep

	def decrementQuota(self):
		"""
		Removes one attempt from the pool of available Quota for that user/ip
		"""
		memcacheKey = "%s-%s-%s" % (self.resource, self._getEndpointKey(), self._getCurrentTimeKey())
		if memcache.incr(memcacheKey) is None:
			memcache.set(memcacheKey, 1, 2 * 60 * self.minutes)

	def isQuotaAvailable(self):
		"""
		Checks if there's currently quota available for the current user/ip
		:return: True if there's quota available, False otherwise
		:rtype: bool
		"""
		endPoint = self._getEndpointKey()
		dateTime = datetime.now()
		secSinceMidnight = (dateTime - dateTime.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()
		currentStep = int(secSinceMidnight / self.secondsPerStep)
		keyBase = dateTime.strftime("%Y-%m-%d-%%s")
		memcacheKeys = []
		for x in range(0, self.steps):
			memcacheKeys.append("%s-%s-%s" % (self.resource, endPoint, keyBase % (currentStep - x)))
		tmpRes = memcache.get_multi(memcacheKeys)
		return sum(tmpRes.values()) <= self.maxRate
