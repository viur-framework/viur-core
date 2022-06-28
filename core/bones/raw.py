from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity


class RawBone(BaseBone):
    """
        Stores it's data without applying any pre/post-processing or filtering. Can be used to store non-html content.
        Use the dot-notation like "raw.markdown" or similar to describe subsequent types.

        ..Warning: Using this bone will lead to security vulnerabilities like reflected XSS unless the data is either
            otherwise validated/stripped or from a trusted source! Don't use this unless you fully understand it's
            implications!

    """
    type = "raw"

    def singleValueFromClient(self, value, skel, name, origData):
        err = self.isInvalid(value)
        if err:
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]
        return value, None
