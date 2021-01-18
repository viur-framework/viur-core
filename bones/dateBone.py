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

	def fromClient(self, skel: 'SkeletonInstance', name: str, data: dict) -> Union[None, List[ReadFromClientError]]:
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
		error = False
		value = self.getEmptyValue()

		if self.date and self.time:
			try:
				time_value = data[name + "-time"]
				date_value = data[name + "-date"]
			except:
				time_value = None
				date_value = None
			finally:
				datetime_value = data[name]

			if datetime_value == "" and time_value is None and date_value is None:
				return [ReadFromClientError(ReadFromClientErrorSeverity.Empty, "Empty value entered")]
		elif self.date:
			date_value = data[name]
			if date_value == "":
				return [ReadFromClientError(ReadFromClientErrorSeverity.Empty, "Empty value entered")]
		elif self.time:
			try:
				time_value = data[name + "-time"]
			except:
				time_value = data[name]

			if time_value == "":
				return [ReadFromClientError(ReadFromClientErrorSeverity.Empty, "Empty value entered")]

		if self.time == True and not time_value == None:
			time_value_raw = time_value
			try:
				if " " in time_value_raw:
					#vi
					year = 1970
					month = 1
					day = 1
					hour = time_value_raw.hour
					month = time_value_raw.minute
					day = time_value_raw.second
					value = datetime(year=year, month=month, day=day, hour=hour, minute=minute, second=second)
				if str(time_value_raw).count(":") == 2:
					(hour, minute, second) = [int(x.strip()) for x in str(time_value_raw).split(":")]
					time_value = datetime(year=1970, month=1, day=1, hour=hour, minute=minute, second=second)
				elif str(time_value_raw).count(":") == 1:
					(hour, minute) = [int(x.strip()) for x in str(time_value_raw).split(":")]
					time_value = datetime(year=1970, month=1, day=1, hour=hour, minute=minute)
				elif str(time_value_raw).replace("-", "", 1).isdigit():
					time_value = datetime(year=1970, month=1, day=1, second=int(time_value_raw))
				else:
					time_value = False  # its invalid
			except:
				time_value = False
		else:
			time_value = None


		if self.date == True and not date_value == None:
			date_value_raw = date_value
			try:
				if " " in date_value_raw:
					#vi
					year = date_value_raw.year
					month = date_value_raw.month
					day = date_value_raw.day
					value = datetime(year=year, month=month, day=day)
				if "-" in date_value_raw:  # ISO (Date only)
					date_value = datetime.strptime(str(date_value_raw), "%Y-%m-%d")
				elif "/" in date_value_raw:  # Ami (Date only)
					date_value = datetime.strptime(str(date_value_raw), "%m/%d/%Y")
				elif "." in date_value_raw:  # European (Date only)
					date_value = datetime.strptime(str(date_value_raw), "%d.%m.%Y")
				else:
					date_value = False
			except:
				date_value = False
		else:
			date_value = None


		#combine time and date value
		if not date_value in [None, False] and not time_value in [None, False]:
			year = date_value.year
			month = date_value.month
			day = date_value.day
			hour = time_value.hour
			minute = time_value.minute
			second = time_value.second
			value = datetime(year=year, month=month, day=day, hour=hour, minute=minute, second=second)
		elif not date_value in [None, False]:
			value = date_value

		elif not time_value in [None, False]:
			value = time_value

		if value == self.getEmptyValue():
			datetime_value_raw = datetime_value

			if str(datetime_value_raw).replace("-", "", 1).replace(".", "", 1).isdigit():
				if int(datetime_value_raw) < -1 * (2 ** 30) or int(datetime_value_raw) > (2 ** 31) - 2:
					error = True  # its invalid
				else:
					datetime_value = datetime.fromtimestamp(float(datetime_value_raw))
			elif str(datetime_value_raw).lower().startswith("now"):
				tmpRes = utcNow().astimezone(self.guessTimeZone())
				if len(str(datetime_value_raw)) > 4:
					try:
						tmpRes += timedelta(seconds=int(str(datetime_value_raw)[3:]))
					except:
						pass
				value = tmpRes
			elif " " in datetime_value:  # Date with time
				try:
					try:  # Times with seconds
						if "-" in datetime_value:  # ISO Date
							value = datetime.strptime(str(datetime_value_raw), "%Y-%m-%d %H:%M:%S")
						elif "/" in datetime_value_raw:  # Ami Date
							value = datetime.strptime(str(datetime_value_raw), "%m/%d/%Y %H:%M:%S")
						else:  # European Date
							value = datetime.strptime(str(datetime_value_raw), "%d.%m.%Y %H:%M:%S")
					except:
						if "-" in datetime_value_raw:  # ISO Date
							value = datetime.strptime(str(datetime_value_raw), "%Y-%m-%d %H:%M")
						elif "/" in datetime_value_raw:  # Ami Date
							value = datetime.strptime(str(datetime_value_raw), "%m/%d/%Y %H:%M")
						else:  # European Date
							value = datetime.strptime(str(datetime_value_raw), "%d.%m.%Y %H:%M")
				except:
					error = True

		if error is True:
			return [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid value entered")]
		err = self.isInvalid(value)
		if err:
			return [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

		timeZone = self.guessTimeZone()
		value = datetime(value.year, value.month, value.day, value.hour, value.minute, value.second, tzinfo=timeZone)
		skel[name] = value
		return  None

	def getEmptyValue(self):
		return datetime(year=1970, month=1, day=1)


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
			if self.date and self.time:
				return value.astimezone(self.guessTimeZone())
			else:
				return value
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
