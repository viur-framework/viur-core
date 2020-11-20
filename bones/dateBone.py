# -*- coding: utf-8 -*-
from viur.core.bones import baseBone
from viur.core import request
from time import time, mktime
from datetime import time, datetime, timedelta
from viur.core.bones.bone import ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.i18n import translate
from viur.core.utils import currentRequest, currentRequestData, utcNow
import logging
from typing import List, Union

try:
	import pytz
except:
	pytz = None

## Workaround for Python Bug #7980 - time.strptime not thread safe
datetime.now().strptime("2010%02d%02d" % (1, 1), "%Y%m%d")
datetime.now().strftime("%Y%m%d")


def datetimeToTimestamp(datetimeObj: datetime) -> int:
	"""Converts this DateTime-Object back into Unixtime"""
	return int(round(mktime(datetimeObj.timetuple())))


class dateBone(baseBone):
	type = "date"

	@staticmethod
	def generageSearchWidget(target, name="DATE BONE", mode="range"):
		return ({"name": name, "mode": mode, "target": target, "type": "date"})

	def __init__(self, creationMagic=False, updateMagic=False, date=True, time=True, localize=False, *args, **kwargs):
		"""
			Initializes a new dateBone.

			:param creationMagic: Use the current time as value when creating an entity; ignoring this bone if the
				entity gets updated.
			:type creationMagic: bool
			:param updateMagic: Use the current time whenever this entity is saved.
			:type updateMagic: bool
			:param date: Should this bone contain a date-information?
			:type date: bool
			:param time: Should this bone contain time information?
			:type time: bool
			:param localize: Automatically convert this time into the users timezone? Only valid if this bone
                                contains date and time-information!
			:type localize: bool
		"""
		baseBone.__init__(self, *args, **kwargs)
		if creationMagic or updateMagic:
			self.readonly = True
		self.creationMagic = creationMagic
		self.updateMagic = updateMagic
		if not (date or time):
			raise ValueError("Attempt to create an empty datebone! Set date or time to True!")
		if localize and not (date and time):
			raise ValueError("Localization is only possible with date and time!")
		if self.multiple and (creationMagic or updateMagic):
			raise ValueError("Cannot be multiple and have a creation/update-magic set!")
		self.date = date
		self.time = time
		self.localize = localize

	def singleValueFromClient(self, value, skel, name, origData):
		"""
			Reads a value from the client.
			If this value is valid for this bone,
			store this value and return None.
			Otherwise our previous value is
			left unchanged and an error-message
			is returned.

			:param name: Our name in the skeleton
			:type name: str
			:param data: *User-supplied* request-data
			:type data: dict
			:returns: str or None
		"""
		rawValue = value
		if str(rawValue).replace("-", "", 1).replace(".", "", 1).isdigit():
			if int(rawValue) < -1 * (2 ** 30) or int(rawValue) > (2 ** 31) - 2:
				value = False  # its invalid
			else:
				value = datetime.fromtimestamp(float(rawValue))
		elif not self.date and self.time:
			try:
				if str(rawValue).count(":") > 1:
					(hour, minute, second) = [int(x.strip()) for x in str(rawValue).split(":")]
					value = datetime(year=1970, month=1, day=1, hour=hour, minute=minute, second=second)
				elif str(rawValue).count(":") > 0:
					(hour, minute) = [int(x.strip()) for x in str(rawValue).split(":")]
					value = datetime(year=1970, month=1, day=1, hour=hour, minute=minute)
				elif str(rawValue).replace("-", "", 1).isdigit():
					value = datetime(year=1970, month=1, day=1, second=int(rawValue))
				else:
					value = False  # its invalid
			except:
				value = False
		elif str(rawValue).lower().startswith("now"):
			tmpRes = utcNow().astimezone(self.guessTimeZone())
			if len(str(rawValue)) > 4:
				try:
					tmpRes += timedelta(seconds=int(str(rawValue)[3:]))
				except:
					pass
			value = tmpRes
		else:
			try:
				timeZone = self.guessTimeZone()
				if " " in rawValue:  # Date with time
					try:  # Times with seconds
						if "-" in rawValue:  # ISO Date
							value = datetime.strptime(str(rawValue), "%Y-%m-%d %H:%M:%S")
						elif "/" in rawValue:  # Ami Date
							value = datetime.strptime(str(rawValue), "%m/%d/%Y %H:%M:%S")
						else:  # European Date
							value = datetime.strptime(str(rawValue), "%d.%m.%Y %H:%M:%S")
					except:
						if "-" in rawValue:  # ISO Date
							value = datetime.strptime(str(rawValue), "%Y-%m-%d %H:%M")
						elif "/" in rawValue:  # Ami Date
							value = datetime.strptime(str(rawValue), "%m/%d/%Y %H:%M")
						else:  # European Date
							value = datetime.strptime(str(rawValue), "%d.%m.%Y %H:%M")
				else:
					if "-" in rawValue:  # ISO (Date only)
						value = datetime.strptime(str(rawValue), "%Y-%m-%d")
					elif "/" in rawValue:  # Ami (Date only)
						value = datetime.strptime(str(rawValue), "%m/%d/%Y")
					else:  # European (Date only)
						value = datetime.strptime(str(rawValue), "%d.%m.%Y")
				value = datetime(value.year, value.month, value.day, value.hour, value.minute, value.second, tzinfo=timeZone)
			except:
				value = False  # its invalid
		if value is False:
			return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, "Invalid value entered")]
		err = self.isInvalid(value)
		if err:
			return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, err)]
		return value, None

	def isInvalid(self, value):
		"""
			Ensure that year is >= 1900
			Otherwise strftime will break later on.
		"""
		if isinstance(value, datetime):
			if value.year < 1900:
				return "Year must be >= 1900"
		return super(dateBone, self).isInvalid(value)

	def guessTimeZone(self):
		"""
		Guess the timezone the user is supposed to be in.
		If it cant be guessed, a safe default (UTC) is used
		"""
		timeZone = pytz.utc  # Default fallback
		currReqData = currentRequestData.get()
		try:
			# Check the local cache first
			if "timeZone" in currReqData:
				return currReqData["timeZone"]
			headers = currentRequest.get().request.headers
			if "X-Appengine-Country" in headers:
				country = headers["X-Appengine-Country"]
			else:  # Maybe local development Server - no way to guess it here
				return timeZone
			tzList = pytz.country_timezones[country]
		except:  # Non-User generated request (deferred call; task queue etc), or no pytz
			return timeZone
		if len(tzList) == 1:  # Fine - the country has exactly one timezone
			timeZone = pytz.timezone(tzList[0])
		elif country.lower() == "us":  # Fallback for the US
			timeZone = pytz.timezone("EST")
		elif country.lower() == "de":  # For some freaking reason Germany is listed with two timezones
			timeZone = pytz.timezone("Europe/Berlin")
		elif country.lower() == "au":
			timeZone = pytz.timezone("Australia/Canberra")  # Equivalent to NSW/Sydney :)
		else:  # The user is in a Country which has more than one timezone
			pass
		currReqData["timeZone"] = timeZone  # Cache the result
		return timeZone

	def singleValueSerialize(self, value, skel: 'SkeletonInstance', name: str, parentIndexed: bool):
		if value:
			# Crop unwanted values to zero
			if not self.time:
				value = value.replace(hour=0, minute=0, second=0, microsecond=0)
			elif not self.date:
				value = value.replace(year=1970, month=1, day=1)
			elif self.date and self.time:
				# This usually happens due to datetime.now(). Use utils.utcNow() instead
				assert value.tzinfo, "Encountered a native Datetime object in %s - refusing to save." % name
		return value

	def singleValueUnserialize(self, value, skel: 'viur.core.skeleton.SkeletonInstance', name: str):
		if isinstance(value, datetime):
			return value.astimezone(self.guessTimeZone())
		else:
			# We got garbage from the datastore
			return None

	def buildDBFilter(self, name, skel, dbFilter, rawFilter, prefix=None):
		for key in [x for x in rawFilter.keys() if x.startswith(name)]:
			resDict = {}
			if not self.fromClient(resDict, key, rawFilter):  # Parsing succeeded
				super(dateBone, self).buildDBFilter(name, skel, dbFilter, {
					key: datetime.now().strptime(resDict[key].strftime("%d.%m.%Y %H:%M:%S"), "%d.%m.%Y %H:%M:%S")},
													prefix=prefix)
		return dbFilter

	def performMagic(self, valuesCache, name, isAdd):
		if (self.creationMagic and isAdd) or self.updateMagic:
			valuesCache[name] = utcNow()
