"""
The PasswordBone class is a specialized version of the StringBone class designed to handle password
data. It hashes the password data before saving it to the database and prevents it from being read
directly. The class also includes various tests to determine the strength of the entered password.
"""
from viur.core.bones.base import ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.bones.string import StringBone
from viur.core.i18n import translate
from viur.core import utils, conf
from hashlib import sha256
import hmac
import codecs
import string
import random
from struct import Struct
from operator import xor
from itertools import starmap
from typing import List, Union


def pbkdf2(password, salt, iterations=1001, keylen=42):
    """
    Implements the PBKDF2 algorithm to generate a cryptographically secure key from a password and
    a salt value.

    This implementation is primarily based on Armin Ronacher's implementation:
    https://github.com/mitsuhiko/python-pbkdf2/blob/master/pbkdf2.py

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.

    :param str password: The password to be used as the basis for the key.
    :param str salt: The salt value to be added to the password to make rainbow table attacks more difficult.
    :param int iterations: The number of iterations the algorithm should go through (default: 1001).
    :param int keylen: The desired length of the resulting key in bytes (default: 42).
    :return: The hashed value of the password in hexadecimal representation.
    :rtype: bytes
    """
    _pack_int = Struct('>I').pack
    if isinstance(password, str):
        password = password.encode("UTF-8")
    if isinstance(salt, str):
        salt = salt.encode("UTF-8")
    mac = hmac.new(password, None, sha256)

    def _pseudorandom(x, mac=mac):
        h = mac.copy()
        h.update(x)
        return h.digest()

    buf = []
    for block in range(1, -(-keylen // mac.digest_size) + 1):
        rv = u = _pseudorandom(salt + _pack_int(block))
        for i in range(iterations - 1):
            u = _pseudorandom((''.join(map(chr, u))).encode("LATIN-1"))
            rv = starmap(xor, zip(rv, u))
        buf.extend(rv)
    return codecs.encode(''.join(map(chr, buf))[:keylen].encode("LATIN-1"), 'hex_codec')


class PasswordBone(StringBone):
    """
    A specialized subclass of the StringBone class designed to handle password data. The
    PasswordBone class hashes the password before saving it to the database and prevents it from
    being read directly. It also includes various tests to determine the strength of the entered
    password.
    """
    type = "password"
    """A string representing the bone type, which is "password" in this case."""
    saltLength = 13
    """The length of the salt used in the hashing process (default: 13)."""
    minPasswordLength = 8
    """The minimum allowed password length (default: 8)."""
    passwordTests = [
        lambda val: val.lower() != val,  # Do we have upper-case characters?
        lambda val: val.upper() != val,  # Do we have lower-case characters?
        lambda val: any([x in val for x in "0123456789"]),  # Do we have any digits?
        lambda val: any([x not in (string.ascii_lowercase + string.ascii_uppercase + string.digits) for x in val]),
        # Special characters?
    ]
    """A list of lambda functions to test the strength of the entered password."""
    passwordTestThreshold = 3
    """The minimum number of password tests that must pass """
    tooShortMessage = translate(
        "core.bones.password.tooShortMessage",
        defaultText="The entered password is to short - it requires at least {{length}} characters."
    )
    """A translated message indicating that the entered password is too short."""
    tooWeakMessage = translate(
        "core.bones.password.tooWeakMessage",
        defaultText="The entered password is too weak."
    )
    """A translated message indicating that the entered password is too weak."""

    def isInvalid(self, value):
        """
        Determines if the entered password is invalid based on the length and strength requirements.
        It checks if the password is empty, too short, or too weak according to the password tests
        specified in the class.

        :param str value: The password to be checked.
        :return: True if the password is invalid, otherwise False.
        :rtype: bool
        """
        if not value:
            return False

        if len(value) < self.minPasswordLength:
            return self.tooShortMessage.translate(length=self.minPasswordLength)

        # Run our password test suite
        testResults = []
        for test in self.passwordTests:
            testResults.append(test(value))

        if sum(testResults) < self.passwordTestThreshold:
            return str(self.tooWeakMessage)

        return False

    def fromClient(self, skel: 'SkeletonInstance', name: str, data: dict) -> Union[None, List[ReadFromClientError]]:
        """
        Processes the password field from the client data, validates it, and stores it in the
        skeleton instance after hashing. This method performs several checks, such as ensuring that
        the password field is present in the data, that the password is not empty, and that it meets
        the length and strength requirements. If any of these checks fail, a ReadFromClientError is
        returned.

        :param SkeletonInstance skel: The skeleton instance to store the password in.
        :param str name: The name of the password field.
        :param dict data: The data dictionary containing the password field value.
        :return: None if the password is valid, otherwise a list of ReadFromClientErrors.
        :rtype: Union[None, List[ReadFromClientError]]
        """
        if not name in data:
            return [ReadFromClientError(ReadFromClientErrorSeverity.NotSet, "Field not submitted")]
        value = data.get(name)
        if not value:
            # Password-Bone is special: As it cannot be read don't set back no None if no value is given
            # This means an once set password can only be changed - but never deleted.
            return [ReadFromClientError(ReadFromClientErrorSeverity.Empty, "No value entered")]
        err = self.isInvalid(value)
        if err:
            return [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]
        # As we don't escape passwords and allow most special characters we'll hash it early on so we don't open
        # an XSS attack vector if a password is echoed back to the client (which should not happen)
        salt = utils.generateRandomString(self.saltLength)
        passwd = pbkdf2(value[: conf["viur.maxPasswordLength"]], salt)
        skel[name] = {"pwhash": passwd, "salt": salt}

    def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
        """
        Processes and stores the password field from the client data into the skeleton instance after
        hashing and validating it. This method carries out various checks, such as:

        * Ensuring that the password field is present in the data.
        * Verifying that the password is not empty.
        * Confirming that the password meets the length and strength requirements.

        If any of these checks fail, a ReadFromClientError is returned.

        :param SkeletonInstance skel: The skeleton instance where the password will be stored as a
            hashed value along with its salt.
        :param str name: The name of the password field used to access the password value in the
            data dictionary.
        :param dict data: The data dictionary containing the password field value, typically
            submitted by the client.
        :return: None if the password is valid and successfully stored in the skeleton instance;
            otherwise, a list of ReadFromClientErrors containing detailed information about the errors.
        :rtype: Union[None, List[ReadFromClientError]]
        """
        if name in skel.accessedValues and skel.accessedValues[name]:
            value = skel.accessedValues[name]
            if isinstance(value, dict):  # It is a pre-hashed value (probably fromClient)
                skel.dbEntity[name] = value
            else:  # This has been set by skel["password"] = "secret", we'll still have to hash it
                salt = utils.generateRandomString(self.saltLength)
                passwd = pbkdf2(value[: conf["viur.maxPasswordLength"]], salt)
                skel.dbEntity[name] = {"pwhash": passwd, "salt": salt}
            # Ensure our indexed flag is up2date
            indexed = self.indexed and parentIndexed
            if indexed and name in skel.dbEntity.exclude_from_indexes:
                skel.dbEntity.exclude_from_indexes.discard(name)
            elif not indexed and name not in skel.dbEntity.exclude_from_indexes:
                skel.dbEntity.exclude_from_indexes.add(name)
            return True
        return False

    def unserialize(self, skeletonValues, name):
        """
        This method does not unserialize password values from the datastore. It always returns False,
        indicating that no password value will be unserialized.

        :param dict skeletonValues: The dictionary containing the values from the datastore.
        :param str name: The name of the password field.
        :return: False, as no password value will be unserialized.
        :rtype: bool
        """
        return False
