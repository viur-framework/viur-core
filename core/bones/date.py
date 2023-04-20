"""
DateBone is a bone that can handle date and/or time information and is derived from the BaseBone class. It can
store date and time information separately, as well as localize the time based on user's timezone.
"""
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
from viur.core import db, request, conf
from viur.core.i18n import translate
from viur.core.utils import currentRequest, currentRequestData, utcNow
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
import pytz
import tzlocal


class DateBone(BaseBone):
    """
    DateBone is a bone that can handle date and/or time information. It can store date and time information
    separately, as well as localize the time based on the user's timezone.

    :param bool creationMagic: Use the current time as value when creating an entity; ignoring this bone if the
        entity gets updated.
    :param bool updateMagic: Use the current time whenever this entity is saved.
    :param bool date: If True, the bone will contain date information.
    :param time: If True, the bone will contain time information.
    :param localize: If True, the user's timezone is assumed for input and output. This is only valid if both 'date'
          and 'time' are set to True. By default, UTC time is used.
    """
    type = "date"

    def __init__(
        self,
        *,
        creationMagic: bool = False,
        date: bool = True,
        localize: bool = False,
        time: bool = True,
        updateMagic: bool = False,
        **kwargs
    ):
        """
            Initializes a new DateBone.

            :param creationMagic: Use the current time as value when creating an entity; ignoring this bone if the
                entity gets updated.
            :param updateMagic: Use the current time whenever this entity is saved.
            :param date: Should this bone contain a date-information?
            :param time: Should this bone contain time information?
            :param localize: Assume users timezone for in and output? Only valid if this bone
                                contains date and time-information! Per default, UTC time is used.
        """
        super().__init__(**kwargs)

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

    def singleValueFromClient(self, value: str, skel: 'viur.core.skeleton.SkeletonInstance', name: str, origData):
        """
        Reads a value from the client. If the value is valid for this bone, it stores the value and returns None.
        Otherwise, the previous value is left unchanged, and an error message is returned.

        The value is assumed to be in the local time zone only if both self.date and self.time are set to True and
        self.localize is True.

            **Value is valid if, when converted into String, it complies following formats:**
                is digit (may include one '-') and valid POSIX timestamp: converted from timestamp;
                assumes UTC timezone

                is digit (may include one '-') and NOT valid POSIX timestamp and not date and time: interpreted as
                seconds after epoch

                'now': current time

                'nowX', where X converted into String is added as seconds to current time

                '%H:%M:%S' if not date and time

                '%M:%S' if not date and time

                '%S' if not date and time

                '%Y-%m-%d %H:%M:%S' (ISO date format)

                '%Y-%m-%d %H:%M' (ISO date format)

                '%Y-%m-%d' (ISO date format)

                '%m/%d/%Y %H:%M:%S' (US date-format)

                '%m/%d/%Y %H:%M' (US date-format)

                '%m/%d/%Y' (US date-format)

                '%d.%m.%Y %H:%M:%S' (EU date-format)

                '%d.%m.%Y %H:%M' (EU date-format)

                '%d.%m.%Y' (EU date-format)


        The resulting year must be >= 1900.

        :param str name: Our name in the skeleton
        :param str value: *User-supplied* request-data, has to be of valid format
        :returns: tuple[datetime or None, [Errors] or None]
        """
        if self.date and self.time and self.localize:
            time_zone = self.guessTimeZone()
        else:
            time_zone = pytz.utc
        rawValue = value
        if str(rawValue).replace("-", "", 1).replace(".", "", 1).isdigit():
            if int(rawValue) < -1 * (2 ** 30) or int(rawValue) > (2 ** 31) - 2:
                value = False  # its invalid
            else:
                value = datetime.fromtimestamp(float(rawValue), tz=time_zone).replace(microsecond=0)
        elif not self.date and self.time:
            try:
                value = time_zone.localize(datetime.fromisoformat(value))
            except:
                try:
                    if str(rawValue).count(":") > 1:
                        (hour, minute, second) = [int(x.strip()) for x in str(rawValue).split(":")]
                        value = datetime(year=1970, month=1, day=1, hour=hour, minute=minute, second=second,
                                         tzinfo=time_zone)
                    elif str(rawValue).count(":") > 0:
                        (hour, minute) = [int(x.strip()) for x in str(rawValue).split(":")]
                        value = datetime(year=1970, month=1, day=1, hour=hour, minute=minute, tzinfo=time_zone)
                    elif str(rawValue).replace("-", "", 1).isdigit():
                        value = datetime(year=1970, month=1, day=1, second=int(rawValue), tzinfo=time_zone)
                    else:
                        value = False  # its invalid
                except:
                    value = False
        elif str(rawValue).lower().startswith("now"):
            tmpRes = datetime.now(time_zone)
            if len(str(rawValue)) > 4:
                try:
                    tmpRes += timedelta(seconds=int(str(rawValue)[3:]))
                except:
                    pass
            value = tmpRes
        else:
            try:
                value = time_zone.localize(datetime.fromisoformat(value))
            except:
                try:
                    if " " in rawValue:  # Date with time
                        try:  # Times with seconds
                            if "-" in rawValue:  # ISO Date
                                value = time_zone.localize(datetime.strptime(str(rawValue), "%Y-%m-%d %H:%M:%S"))
                            elif "/" in rawValue:  # Ami Date
                                value = time_zone.localize(datetime.strptime(str(rawValue), "%m/%d/%Y %H:%M:%S"))
                            else:  # European Date
                                value = time_zone.localize(datetime.strptime(str(rawValue), "%d.%m.%Y %H:%M:%S"))
                        except:
                            if "-" in rawValue:  # ISO Date
                                value = time_zone.localize(datetime.strptime(str(rawValue), "%Y-%m-%d %H:%M"))
                            elif "/" in rawValue:  # Ami Date
                                value = time_zone.localize(datetime.strptime(str(rawValue), "%m/%d/%Y %H:%M"))
                            else:  # European Date
                                value = time_zone.localize(datetime.strptime(str(rawValue), "%d.%m.%Y %H:%M"))
                    else:
                        if "-" in rawValue:  # ISO (Date only)
                            value = time_zone.localize(datetime.strptime(str(rawValue), "%Y-%m-%d"))
                        elif "/" in rawValue:  # Ami (Date only)
                            value = time_zone.localize(datetime.strptime(str(rawValue), "%m/%d/%Y"))
                        else:  # European (Date only)
                            value = time_zone.localize(datetime.strptime(str(rawValue), "%d.%m.%Y"))
                except:
                    value = False  # its invalid
        if value is False:
            return self.getEmptyValue(), [
                ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid value entered")]
        value = value.replace(microsecond=0)
        err = self.isInvalid(value)
        if err:
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]
        return value, None

    def isInvalid(self, value):
        """
        Validates the input value to ensure that the year is greater than or equal to 1900. If the year is less
        than 1900, it returns an error message. Otherwise, it calls the superclass's isInvalid method to perform
        any additional validations.

        This check is important because the strftime function, which is used to format dates in Python, will
        break if the year is less than 1900.

        :param datetime value: The input value to be validated, expected to be a datetime object.

        :returns: An error message if the year is less than 1900, otherwise the result of calling
            the superclass's isInvalid method.
        :rtype: str or None
        """
        if isinstance(value, datetime):
            if value.year < 1900:
                return "Year must be >= 1900"

        return super().isInvalid(value)

    def guessTimeZone(self):
        """
        Tries to guess the user's time zone based on request headers. If the time zone cannot be guessed, it
        falls back to using the UTC time zone. The guessed time zone is then cached for future use during the
        current request.

        :returns: The guessed time zone for the user or a default time zone (UTC) if the time zone cannot be guessed.
        :rtype: pytz timezone object
        """
        timeZone = pytz.utc  # Default fallback
        currReqData = currentRequestData.get()
        if conf["viur.instance.is_dev_server"]:
            return tzlocal.get_localzone()
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
        """
        Prepares a single value for storage by removing any unwanted parts of the datetime object, such as
        microseconds or adjusting the date and time components depending on the configuration of the dateBone.
        The method also ensures that the datetime object is timezone aware.

        :param datetime value: The input datetime value to be serialized.
        :param SkeletonInstance skel: The instance of the skeleton that contains this bone.
        :param str name: The name of the bone in the skeleton.
        :param bool parentIndexed: A boolean indicating if the parent bone is indexed.
        :returns: The serialized datetime value with unwanted parts removed and timezone-aware.
        :rtype: datetime
        """
        if value:
            # Crop unwanted values to zero
            value = value.replace(microsecond=0)
            if not self.time:
                value = value.replace(hour=0, minute=0, second=0)
            elif not self.date:
                value = value.replace(year=1970, month=1, day=1)
            # We should always deal with timezone aware datetimes
            assert value.tzinfo, "Encountered a naive Datetime object in %s - refusing to save." % name
        return value

    def singleValueUnserialize(self, value):
        """
        Converts the serialized datetime value back to its original form. If the datetime object is timezone aware,
        it adjusts the timezone based on the configuration of the dateBone.

        :param datetime value: The input serialized datetime value to be unserialized.
        :returns: The unserialized datetime value with the appropriate timezone applied or None if the input
            value is not a valid datetime object.
        :rtype: datetime or None
        """
        if isinstance(value, datetime):
            # Serialized value is timezone aware.
            # If local timezone is needed, set here, else force UTC.
            if self.date and self.time and self.localize:
                time_zone = self.guessTimeZone()
            else:
                time_zone = pytz.utc
            return value.astimezone(time_zone)
        else:
            # We got garbage from the datastore
            return None

    def buildDBFilter(self,
                      name: str,
                      skel: 'viur.core.skeleton.SkeletonInstance',
                      dbFilter: db.Query,
                      rawFilter: Dict,
                      prefix: Optional[str] = None) -> db.Query:
        """
        Constructs a datastore filter for date and/or time values based on the given raw filter. It parses the
        raw filter and, if successful, applies it to the datastore query.

        :param str name: The name of the dateBone in the skeleton.
        :param SkeletonInstance skel: The skeleton instance containing the dateBone.
        :param db.Query dbFilter: The datastore query to which the filter will be applied.
        :param Dict rawFilter: The raw filter dictionary containing the filter values.
        :param Optional[str] prefix: An optional prefix to use for the filter key, defaults to None.
        :returns: The datastore query with the constructed filter applied.
        :rtype: db.Query
        """
        for key in [x for x in rawFilter.keys() if x.startswith(name)]:
            resDict = {}
            if not self.fromClient(resDict, key, rawFilter):  # Parsing succeeded
                super().buildDBFilter(name, skel, dbFilter, {key: resDict[key]}, prefix=prefix)

        return dbFilter

    def performMagic(self, valuesCache, name, isAdd):
        """
        Automatically sets the current date and/or time for a dateBone when a new entry is created or an
        existing entry is updated, depending on the configuration of creationMagic and updateMagic.

        :param dict valuesCache: The cache of values to be stored in the datastore.
        :param str name: The name of the dateBone in the skeleton.
        :param bool isAdd: A flag indicating whether the operation is adding a new entry (True) or updating an
            existing one (False).
        """
        if (self.creationMagic and isAdd) or self.updateMagic:
            valuesCache[name] = utcNow().replace(microsecond=0).astimezone(self.guessTimeZone())
