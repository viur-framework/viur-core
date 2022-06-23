from viur.core import db, errors, utils
from viur.core.tasks import PeriodicTask, DeleteEntitiesIter
from typing import Literal, Union
from datetime import timedelta


class RateLimit(object):
    """
        This class is used to restrict access to certain functions to *maxRate* calls per minute.

        Usage: Create an instance of this object in you modules __init__ function. then call
        isQuotaAvailable before executing the action to check if there is quota available and
        after executing the action decrementQuota.

    """
    rateLimitKind = "viur-ratelimit"

    def __init__(self, resource: str, maxRate: int, minutes: int, method: Literal["ip", "user"]):
        """
        Initializes a new RateLimit gate.

        :param resource: Name of the resource to protect
        :param maxRate: Amount of tries allowed in the give time-span
        :param minutes: Length of the time-span in minutes
        :param method: Lock by IP or by the current user
        """
        super(RateLimit, self).__init__()
        self.resource = resource
        self.maxRate = maxRate
        self.minutes = minutes
        self.steps = min(minutes, 5)
        self.secondsPerStep = 60 * (float(minutes) / float(self.steps))
        assert method in ["ip", "user"], "method must be 'ip' or 'user'"
        self.useUser = method == "user"

    def _getEndpointKey(self) -> Union[db.Key, str]:
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
            remoteAddr = utils.currentRequest.get().request.remote_addr
            if "::" in remoteAddr:  # IPv6 in shorted form
                remoteAddr = remoteAddr.split(":")
                blankIndex = remoteAddr.index("")
                missigParts = ["0000"] * (8 - len(remoteAddr))
                remoteAddr = remoteAddr[:blankIndex] + missigParts + remoteAddr[blankIndex + 1:]
                return ":".join(remoteAddr[:4])
            elif ":" in remoteAddr:  # It's IPv6, so we remove the last 64 bits (interface id)
                # as it is easily controlled by the user
                return ":".join(remoteAddr.split(":")[:4])
            else:  # It's IPv4, simply return that address
                return remoteAddr

    def _getCurrentTimeKey(self) -> str:
        """
        :return: the current lockperiod used in second position of the memcache key
        """
        dateTime = utils.utcNow()
        key = dateTime.strftime("%Y-%m-%d-%%s")
        secsinceMidnight = (dateTime - dateTime.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()
        currentStep = int(secsinceMidnight / self.secondsPerStep)
        return key % currentStep

    def decrementQuota(self) -> None:
        """
        Removes one attempt from the pool of available Quota for that user/ip
        """

        def updateTxn(cacheKey: str) -> None:
            key = db.Key(self.rateLimitKind, cacheKey)
            obj = db.Get(key)
            if obj is None:
                obj = db.Entity(key)
                obj["value"] = 0
            obj["value"] += 1
            obj["expires"] = utils.utcNow() + timedelta(minutes=2 * self.minutes)
            db.Put(obj)

        lockKey = "%s-%s-%s" % (self.resource, self._getEndpointKey(), self._getCurrentTimeKey())
        db.RunInTransaction(updateTxn, lockKey)

    def isQuotaAvailable(self) -> bool:
        """
        Checks if there's currently quota available for the current user/ip
        :return: True if there's quota available, False otherwise
        """
        endPoint = self._getEndpointKey()
        currentDateTime = utils.utcNow()
        secSinceMidnight = (currentDateTime - currentDateTime.replace(hour=0, minute=0, second=0,
                                                                      microsecond=0)).total_seconds()
        currentStep = int(secSinceMidnight / self.secondsPerStep)
        keyBase = currentDateTime.strftime("%Y-%m-%d-%%s")
        cacheKeys = []
        for x in range(0, self.steps):
            cacheKeys.append(
                db.Key(self.rateLimitKind, "%s-%s-%s" % (self.resource, endPoint, keyBase % (currentStep - x))))
        tmpRes = db.Get(cacheKeys)
        return sum([x["value"] for x in tmpRes if x and currentDateTime < x["expires"]]) <= self.maxRate

    def assertQuotaIsAvailable(self, setRetryAfterHeader: bool = True) -> bool:
        """Assert quota is available.

        If not quota is available a :class:`viur.core.errors.TooManyRequests`
        exception will be raised.

        :param setRetryAfterHeader: Set the Retry-After header on the
            current request response, if the quota is exceeded.
        :return: True if quota is available.
        :raises: :exc:`viur.core.errors.TooManyRequests`, if no quote is available.
        """
        if self.isQuotaAvailable():
            return True
        if setRetryAfterHeader:
            utils.currentRequest.get().response.headers["Retry-After"] = str(self.maxRate * 60)

        raise errors.TooManyRequests(
            f"{self.steps} requests allowed per {self.maxRate} minute(s). Try again later."
        )


@PeriodicTask(60)
def cleanOldRateLocks(*args, **kwargs) -> None:
    DeleteEntitiesIter.startIterOnQuery(db.Query(RateLimit.rateLimitKind).filter("expires <", utils.utcNow()))
