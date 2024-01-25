from datetime import datetime, timedelta, timezone
import typing as t

import pytz
import tzlocal

from viur.core import conf, current, db
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.utils import utcNow


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
    # FIXME: the class has no parameters; merge with __init__
    type = "date"

    def __init__(
        self,
        *,
        creationMagic: bool = False,
        date: bool = True,
        localize: bool = None,
        naive: bool = False,
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
            :param naive: Use naive datetime for this bone, the default is aware.
        """
        super().__init__(**kwargs)

        # Either date or time must be set
        if not (date or time):
            raise ValueError("Attempt to create an empty DateBone! Set date or time to True!")

        # Localize-flag only possible with date and time
        if localize and not (date and time):
            raise ValueError("Localization is only possible with date and time!")
        # Default localize all DateBones, if not explicitly defined
        elif localize is None and not naive:
            localize = date and time

        if naive and localize:
            raise ValueError("Localize and naive is not possible!")

        # Magic is only possible in non-multiple bones and why ever only on readonly bones...
        if creationMagic or updateMagic:
            if self.multiple:
                raise ValueError("Cannot be multiple and have a creation/update-magic set!")

            self.readonly = True  # todo: why???

        self.creationMagic = creationMagic
        self.updateMagic = updateMagic
        self.date = date
        self.time = time
        self.localize = localize
        self.naive = naive

    def singleValueFromClient(self, value, skel, bone_name, client_data):
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

        :param bone_name: Our name in the skeleton
        :param client_data: *User-supplied* request-data, has to be of valid format
        :returns: tuple[datetime or None, [Errors] or None]
        """
        time_zone = self.guessTimeZone()
        value = str(value)  # always enforce value to be a str

        if value.replace("-", "", 1).replace(".", "", 1).isdigit():
            if int(value) < -1 * (2 ** 30) or int(value) > (2 ** 31) - 2:
                value = None
            else:
                value = datetime.fromtimestamp(float(value), tz=time_zone).replace(microsecond=0)

        elif not self.date and self.time:
            try:
                value = datetime.fromisoformat(value)

            except ValueError:
                try:
                    if value.count(":") > 1:
                        (hour, minute, second) = [int(x.strip()) for x in value.split(":")]
                        value = datetime(year=1970, month=1, day=1, hour=hour, minute=minute, second=second,
                                         tzinfo=time_zone)
                    elif value.count(":") > 0:
                        (hour, minute) = [int(x.strip()) for x in value.split(":")]
                        value = datetime(year=1970, month=1, day=1, hour=hour, minute=minute, tzinfo=time_zone)
                    elif value.replace("-", "", 1).isdigit():
                        value = datetime(year=1970, month=1, day=1, second=int(value), tzinfo=time_zone)
                    else:
                        value = None

                except ValueError:
                    value = None

        elif value.lower().startswith("now"):
            now = datetime.now(time_zone)
            if len(value) > 4:
                try:
                    now += timedelta(seconds=int(value[3:]))
                except ValueError:
                    now = None

            value = now

        else:
            # try to parse ISO-formatted date string
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                # otherwise, test against several format strings
                for fmt in (
                    "%Y-%m-%d %H:%M:%S",
                    "%m/%d/%Y %H:%M:%S",
                    "%d.%m.%Y %H:%M:%S",
                    "%Y-%m-%d %H:%M",
                    "%m/%d/%Y %H:%M",
                    "%d.%m.%Y %H:%M",
                    "%Y-%m-%d",
                    "%m/%d/%Y",
                    "%d.%m.%Y",
                ):
                    try:
                        value = datetime.strptime(value, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    value = None

        if not value:
            return self.getEmptyValue(), [
                ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid value entered")
            ]

        if value.tzinfo and self.naive:
            return self.getEmptyValue(), [
                ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Datetime must be naive")
            ]

        if not value.tzinfo and not self.naive:
            value = time_zone.localize(value)

        # remove microseconds
        # TODO: might become configurable
        value = value.replace(microsecond=0)

        if err := self.isInvalid(value):
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
        if self.naive:
            return None
        if not (self.date and self.time and self.localize):
            return pytz.utc

        if conf.instance.is_dev_server:
            return pytz.timezone(tzlocal.get_localzone_name())

        timeZone = pytz.utc  # Default fallback
        currReqData = current.request_data.get()

        try:
            # Check the local cache first
            if "timeZone" in currReqData:
                return currReqData["timeZone"]
            headers = current.request.get().request.headers
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
            if self.naive:
                value = value.replace(tzinfo=timezone.utc)
            # We should always deal with timezone aware datetimes
            assert value.tzinfo, f"Encountered a naive Datetime object in {name} - refusing to save."
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
            if self.naive:
                value = value.replace(tzinfo=None)
                return value
            else:
                # If local timezone is needed, set here, else force UTC.
                time_zone = self.guessTimeZone()
                return value.astimezone(time_zone)
        else:
            # We got garbage from the datastore
            return None

    def buildDBFilter(self,
                      name: str,
                      skel: 'viur.core.skeleton.SkeletonInstance',
                      dbFilter: db.Query,
                      rawFilter: dict,
                      prefix: t.Optional[str] = None) -> db.Query:
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
            if self.naive:
                valuesCache[name] = utcNow().replace(microsecond=0, tzinfo=None)
            else:
                valuesCache[name] = utcNow().replace(microsecond=0).astimezone(self.guessTimeZone())

    def structure(self) -> dict:
        return super().structure() | {
            "date": self.date,
            "time": self.time,
            "naive": self.naive
        }
