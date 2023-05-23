from viur.core.bones.base import ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.bones.string import StringBone


class CredentialBone(StringBone):
    """
        A bone for storing credentials.
        This is always empty if read from the database.
        If its saved, its ignored if its values is still empty.
        If its value is not empty, it will update the value in the database
    """
    type = "str.credential"

    def __init__(
        self,
        *,
        maxLength: int = None,  # Unlimited length
        **kwargs
    ):
        super().__init__(maxLength=maxLength, **kwargs)
        if self.multiple or self.languages:
            raise ValueError("Credential-Bones cannot be multiple or translated!")

    def isInvalid(self, value):
        """
            Returns None if the value would be valid for
            this bone, an error-message otherwise.
        """
        if value is None:
            return False
        if self.maxLength is not None and len(value) > self.maxLength:
            return "Maximum length exceeded"

    def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
        """
            Update the value only if a new value is supplied.
        """
        skel.dbEntity.exclude_from_indexes.add(name)  # Ensure we are never indexed
        if name in skel.accessedValues and skel.accessedValues[name]:
            skel.dbEntity[name] = skel.accessedValues[name]
            return True
        return False

    def unserialize(self, valuesCache, name):
        """
            We'll never read our value from the database.
        """
        return {}

    def singleValueFromClient(self, value, skel, name, origData):
        if not (err := self.isInvalid(value)):
            return value, None
        return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]
