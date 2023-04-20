"""
A bone for storing credentials.

This bone is designed to store sensitive information like passwords, API keys, or other secret strings. It ensures that the stored value is always empty when read from the database. When saved, the value is only updated in the database if it is non-empty.
"""

from viur.core.bones.base import ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.bones.string import StringBone
from viur.core import utils


class CredentialBone(StringBone):
    """
        A bone for storing credentials. This bone is designed to store sensitive information like
        passwords, API keys, or other secret strings.
        This is always empty if read from the database.
        If its saved, its ignored if its values is still empty.
        If its value is not empty, it will update the value in the database

        :ivar str type: The type identifier of the bone, set to "str.credential".

    """
    type = "str.credential"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.multiple or self.languages:
            raise ValueError("Credential-Bones cannot be multiple or translated!")

    def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
        """
        Serializes the bone's value for storage.

        Updates the value in the database only if a new value is supplied. Ensures the value is
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
        Unserializes the bone's value from storage.

        This method always returns an empty dictionary as the CredentialBone's value is always empty when read from the database.

        :param dict valuesCache: A dictionary containing the serialized values from the datastore.
        :param str name: The name of the bone attribute.
        :return: An empty dictionary, as the CredentialBone's value is always empty when read from the database.
        :rtype: dict
        """
        return {}

    def singleValueFromClient(self, value, skel, name, origData):
        """
        Processes the value received from the client.

        Returns the escaped value if it is valid, or the empty value and an error if the value is invalid.

        :param value: The value received from the client.
        :param skel: The skeleton instance that the bone is part of.
        :type skel: SkeletonInstance
        :param str name: The name of the bone attribute.
        :param origData: The original data received from the client.
        :return: A tuple containing the escaped value and None if the value is valid, or the empty value and a ReadFromClientError if the value is invalid.
        :rtype: tuple
        """
        err = self.isInvalid(value)
        if not err:
            return utils.escapeString(value, 4 * 1024), None
        return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]
