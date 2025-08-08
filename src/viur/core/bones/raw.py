import re
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity

SEARCH_TAGS = re.compile(r"\w+")


class RawBone(BaseBone):
    """
    Stores its data without applying any pre/post-processing or filtering. Can be used to store
    non-html content.
    Use the dot-notation like "raw.markdown" or similar to describe subsequent types.

    ..Warning: Using this bone will lead to security vulnerabilities like reflected XSS unless the
        data is either otherwise validated/stripped or from a trusted source! Don't use this unless
        you fully understand it's implications!
    """
    type = "raw"

    def singleValueFromClient(self, value, skel, bone_name, client_data):
        err = self.isInvalid(value)
        if err:
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]
        return value, None

    def getSearchTags(self, skel: "SkeletonInstance", name: str) -> set[str]:
        result = set()

        for idx, lang, value in self.iter_bone_value(skel, name):
            if not value:
                continue

            for tag in re.finditer(SEARCH_TAGS, str(value)):
                result.add(tag.group())

        return result
