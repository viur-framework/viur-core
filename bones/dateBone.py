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


class ExtendedDateTime(datetime):
	def totimestamp(self):
		"""Converts this DateTime-Object back into Unixtime"""
		return (int(round(mktime(self.timetuple()))))

	def strftime(self, format):
		"""
		Provides correct localized names for directives like %a which dont get translated on GAE properly
		This currently replaces %a, %A, %b, %B, %c, %x and %X.

		:param format: String containing the Format to apply.
		:type format: str
		:returns: str
		"""
		if "%c" in format:
			format = format.replace("%c", translate("const_datetimeformat"))
		if "%x" in format:
			format = format.replace("%x", translate("const_dateformat"))
		if "%X" in format:
			format = format.replace("%X", translate("const_timeformat"))
		if "%a" in format:
			format = format.replace("%a", translate("const_day_%s_short" % int(super(ExtendedDateTime, self).strftime("%w"))))
		if "%A" in format:
			format = format.replace("%A", translate("const_day_%s_long" % int(super(ExtendedDateTime, self).strftime("%w"))))
		if "%b" in format:
			format = format.replace("%b", translate("const_month_%s_short" % int(super(ExtendedDateTime, self).strftime("%m"))))
		if "%B" in format:
			format = format.replace("%B", translate("const_month_%s_long" % int(super(ExtendedDateTime, self).strftime("%m"))))
		return super(ExtendedDateTime, self).strftime(format)


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
		if not rawValue:
			return None, [ReadFromClientError(ReadFromClientErrorSeverity.Empty, name, "No value selected")]
		elif str(rawValue).replace("-", "", 1).replace(".", "", 1).isdigit():
			if int(rawValue) < -1 * (2 ** 30) or int(rawValue) > (2 ** 31) - 2:
				value = False  # its invalid
			else:
				value = ExtendedDateTime.fromtimestamp(float(rawValue))
		elif not self.date and self.time:
			try:
				if str(rawValue).count(":") > 1:
					(hour, minute, second) = [int(x.strip()) for x in str(rawValue).split(":")]
					value = time(hour=hour, minute=minute, second=second)
				elif str(rawValue).count(":") > 0:
					(hour, minute) = [int(x.strip()) for x in str(rawValue).split(":")]
					value = time(hour=hour, minute=minute)
				elif str(rawValue).replace("-", "", 1).isdigit():
					value = time(second=int(rawValue))
				else:
					value = False  # its invalid
			except:
				value = False
		elif str(rawValue).lower().startswith("now"):
			tmpRes = ExtendedDateTime.now()
			if len(str(rawValue)) > 4:
				try:
					tmpRes += timedelta(seconds=int(str(rawValue)[3:]))
				except:
					pass
			value = tmpRes
		else:
			try:
				if " " in rawValue:  # Date with time
					try:  # Times with seconds
						if "-" in rawValue:  # ISO Date
							value = ExtendedDateTime.strptime(str(rawValue), "%Y-%m-%d %H:%M:%S")
						elif "/" in rawValue:  # Ami Date
							value = ExtendedDateTime.strptime(str(rawValue), "%m/%d/%Y %H:%M:%S")
						else:  # European Date
							value = ExtendedDateTime.strptime(str(rawValue), "%d.%m.%Y %H:%M:%S")
					except:
						if "-" in rawValue:  # ISO Date
							value = ExtendedDateTime.strptime(str(rawValue), "%Y-%m-%d %H:%M")
						elif "/" in rawValue:  # Ami Date
							value = ExtendedDateTime.strptime(str(rawValue), "%m/%d/%Y %H:%M")
						else:  # European Date
							value = ExtendedDateTime.strptime(str(rawValue), "%d.%m.%Y %H:%M")
				else:
					if "-" in rawValue:  # ISO (Date only)
						value = ExtendedDateTime.strptime(str(rawValue), "%Y-%m-%d")
					elif "/" in rawValue:  # Ami (Date only)
						value = ExtendedDateTime.strptime(str(rawValue), "%m/%d/%Y")
					else:  # European (Date only)
						value = ExtendedDateTime.strptime(str(rawValue), "%d.%m.%Y")
			except:
				value = False  # its invalid
		if value is False:
			return None, [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, "Invalid value entered")]
		err = self.isInvalid(value)
		if err:
			return [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, err)]
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
		timeZone = "UTC"  # Default fallback
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
			timeZone = tzList[0]
		elif country.lower() == "us":  # Fallback for the US
			timeZone = "EST"
		elif country.lower() == "de":  # For some freaking reason Germany is listed with two timezones
			timeZone = "Europe/Berlin"
		else:  # The user is in a Country which has more than one timezone
			# Fixme: Is there any equivalent of EST for australia?
			pass
			currReqData["timeZone"] = timeZone  # Cache the result
		return timeZone

	def readLocalized(self, value):
		"""Read a (probably localized Value) from the Client and convert it back to UTC"""
		res = value
		if not self.localize or not value or not isinstance(value, datetime):
			return (res)
		# Nomalize the Date to UTC
		timeZone = self.guessTimeZone()
		if timeZone != "UTC" and pytz:
			utc = pytz.utc
			tz = pytz.timezone(timeZone)
			# FIXME: This is ugly as hell.
			# Parsing a Date which is inside DST of the given tz dosnt change the tz-info,
			# and normalizing the whole thing changes the other values, too
			# So we parse the whole thing, normalize it (=>get the correct DST-Settings), then replacing the parameters again
			# and pray that the DST-Settings are still valid..
			res = ExtendedDateTime(value.year, value.month, value.day, value.hour, value.minute, value.second,
								   tzinfo=tz)
			res = tz.normalize(res)  # Figure out if its in DST or not
			res = res.replace(year=value.year, month=value.month, day=value.day, hour=value.hour, minute=value.minute,
							  second=value.second)  # Reset the original values
			res = utc.normalize(res.astimezone(utc))
		return (res)

	def singleValueSerialize(self, value, skel: 'SkeletonInstance', name: str, parentIndexed: bool):
		if value:
			value = self.readLocalized(datetime.now().strptime(value.strftime("%d.%m.%Y %H:%M:%S"), "%d.%m.%Y %H:%M:%S"))
				# Crop unwanted values to zero
			if not self.time:
				value = value.replace(hour=0, minute=0, second=0, microsecond=0)
			elif not self.date:
				value = value.replace(year=1970, month=1, day=1)
		return value

	def singleValueUnserialize(self, value, skel: 'viur.core.skeleton.SkeletonInstance', name: str):
		if value and (isinstance(value, float) or isinstance(value, int)):
			if self.date:
				return self.setLocalized(skel, name, ExtendedDateTime.fromtimestamp(value))
			else:
				# FIXME! Seconds?
				return time(hour=int(value / 60), minute=int(value % 60))
		elif isinstance(value, datetime):
			return self.setLocalized(skel, name,
							  ExtendedDateTime.now().strptime(value.strftime("%d.%m.%Y %H:%M:%S"),
															  "%d.%m.%Y %H:%M:%S"))
		else:
			# We got garbarge from the datastore
			return None

	def setLocalized(self, skeletonValues, name, value):
		""" Converts a Date read from DB (UTC) to the requesters local time"""
		if not self.localize or not value or not isinstance(value, ExtendedDateTime):
			return value
		timeZone = self.guessTimeZone()
		if timeZone != "UTC" and pytz:
			utc = pytz.utc
			tz = pytz.timezone(timeZone)
			value = tz.normalize(value.replace(tzinfo=utc).astimezone(tz))
			value = ExtendedDateTime(value.year, value.month, value.day,
									 value.hour, value.minute, value.second)
		return value

	def buildDBFilter(self, name, skel, dbFilter, rawFilter, prefix=None):
		for key in [x for x in rawFilter.keys() if x.startswith(name)]:
			resDict = {}
			if not self.fromClient(resDict, key, rawFilter):  # Parsing succeeded
				super(dateBone, self).buildDBFilter(name, skel, dbFilter, {
					key: datetime.now().strptime(resDict[key].strftime("%d.%m.%Y %H:%M:%S"), "%d.%m.%Y %H:%M:%S")},
													prefix=prefix)
		return (dbFilter)

	def performMagic(self, valuesCache, name, isAdd):
		if (self.creationMagic and isAdd) or self.updateMagic:
			valuesCache[name] = utcNow()
