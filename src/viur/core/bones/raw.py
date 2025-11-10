import re
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity

SEARCH_TAGS = re.compile(r"[^\s]+")


class RawBone(BaseBone):
    """
    Stores its data without applying any pre/post-processing or filtering.
    Can be used to store any textual content.

    Use the dot-notation like "raw.code.markdown" or similar to describe subsequent types.
    This can also be achieved by adding `type_suffix="code.markdown"` to the RawBone's instantiation.

    ..Warning: Using this bone will lead to security vulnerabilities like reflected XSS unless the
        data is either otherwise validated/stripped or from a trusted source! Don't use this unless
        you fully understand it's implications!
    """
    type = "raw"

    def singleValueFromClient(self, value, skel, bone_name, client_data):
        if err := self.isInvalid(value):
            return value, [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

        return value, None

    def getSearchTags(self, skel: "SkeletonInstance", name: str) -> set[str]:
        result = set()

        for idx, lang, value in self.iter_bone_value(skel, name):
            if not value:
                continue

            for tag in re.finditer(SEARCH_TAGS, str(value)):
                result.add(tag.group())

        return result
