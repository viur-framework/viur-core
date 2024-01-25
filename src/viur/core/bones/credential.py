from viur.core.bones.base import ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.bones.string import StringBone


class CredentialBone(StringBone):
    """
        A bone for storing credentials. This bone is designed to store sensitive information like
        passwords, API keys, or other secret strings.
        This is always empty if read from the database.
        If it's saved, its ignored if its values is still empty.
        If its value is not empty, it will update the value in the database

        :ivar str type: The type identifier of the bone, set to "str.credential".
    """
    type = "str.credential"

    def __init__(
        self,
        *,
        max_length: int = None,  # Unlimited length
        **kwargs
    ):

        super().__init__(max_length=max_length, **kwargs)
        if self.multiple or self.languages:
            raise ValueError("CredentialBone cannot be multiple or translated")

    def isInvalid(self, value):
        """
            Returns None if the value would be valid for
            this bone, an error-message otherwise.
        """
        if value is None:
            return False
        if self.max_length is not None and len(value) > self.max_length:
            return "Maximum length exceeded"

    def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
        """
        Serializes the bone's value for the database.

        Updates the value in the entity only if a new value is supplied. Ensures the value is
        never indexed.

        :param skel: The skeleton instance that the bone is part of.
        :type skel: SkeletonInstance
        :param str name: The name of the bone attribute.
        :param bool parentIndexed: Indicates whether the parent entity is indexed.
        :return: True if the value was updated in the database, False otherwise.
        :rtype: bool
        """
        skel.dbEntity.exclude_from_indexes.add(name)  # Ensure we are never indexed
        if name in skel.accessedValues and skel.accessedValues[name]:
            skel.dbEntity[name] = skel.accessedValues[name]
            return True
        return False

    def unserialize(self, valuesCache, name):
        """
        Unserializes the bone's value from the database.

        This method always returns an empty dictionary as the CredentialBone's value is always empty when read from
        the database.

        :param dict valuesCache: A dictionary containing the serialized values from the datastore.
        :param str name: The name of the bone attribute.
        :return: An empty dictionary, as the CredentialBone's value is always empty when read from the database.
        :rtype: dict
        """
        return {}

    def singleValueFromClient(self, value, skel, bone_name, client_data):
        if not (err := self.isInvalid(value)):
            return value, None

        return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]
