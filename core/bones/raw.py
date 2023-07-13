"""
The RawBone stores it's data without applying any pre/post-processing or filtering. Can be used to
store non-html content.
"""
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity


class RawBone(BaseBone):
    """
    Stores it's data without applying any pre/post-processing or filtering. Can be used to store
    non-html content.
    Use the dot-notation like "raw.markdown" or similar to describe subsequent types.

    ..Warning: Using this bone will lead to security vulnerabilities like reflected XSS unless the
        data is either otherwise validated/stripped or from a trusted source! Don't use this unless
        you fully understand it's implications!
    """
    type = "raw"

    def singleValueFromClient(self, value, skel, name, origData):
        """
        Takes a value from the client, checks if it's invalid, and returns either the value with no
        errors or an empty value with an error.

        :param value: The value to be checked.
        :param skel: The :class:viur.core.skeleton.Skeleton instance this bone is part of.
        :param name: The property-name this bone has in its Skeleton (not the description!).
        :param origData: The original data received from the client.
        :returns: A tuple containing the value and either an error or None. If the value is invalid,
            returns an empty value and a ReadFromClientError. Otherwise, returns the value and None.
        """
        err = self.isInvalid(value)
        if err:
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]
        return value, None
