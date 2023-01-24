from viur.core.bones.base import ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.bones.string import StringBone
from viur.core.i18n import translate
from viur.core import utils, conf
from hashlib import sha256
import hmac
import codecs
import re
from struct import Struct
from operator import xor
from itertools import starmap
from typing import List, Tuple, Union


def pbkdf2(password, salt, iterations=1001, keylen=42):
    """
        An implementation of PBKDF2 (http://wikipedia.org/wiki/PBKDF2)

        Mostly based on the implementation of
        https://github.com/mitsuhiko/python-pbkdf2/blob/master/pbkdf2.py

        :copyright: (c) Copyright 2011 by Armin Ronacher.
        :license: BSD, see LICENSE for more details.
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
        A bone holding passwords.
        This is always empty if read from the database.
        If its saved, its ignored if its values is still empty.
        If its value is not empty, its hashed (with salt) and only the resulting hash
        will be written to the database
    """
    type = "password"
    saltLength = 13

    tooShortMessage = translate(
        "core.bones.password.tooShortMessage",
        defaultText="The entered password is to short - it requires at least {{length}} characters."
    )
    tooWeakMessage = translate(
        "core.bones.password.tooWeakMessage",
        defaultText="The entered password is too weak."
    )
    password_tests: List[Tuple] = [
        (r"^.*[A-Z].*$", translate("core.bones.password.no_capital_letters",
                                   defaultText="The password entered has no capital letters.")),
        (r"^.*[a-z].*$", translate("core.bones.password.no_lowercase_letters",
                                   defaultText="The password entered has no lowercase letters.")),
        (r"^.*\d.*$", translate("core.bones.password.no_digits",
                                defaultText="The password entered has no digits.")),
        (r"^.*\W.*$", translate("core.bones.password.no_special_characters",
                                defaultText="The password entered has no special characters.")),

    ]

    def __init__(
        self,
        *,
        min_password_length: int = 8,
        test_threshold: int = 3,
        password_tests: List[Tuple] = password_tests,
        **kwargs
    ):
        """
            Initializes a new Password Bone.

            :param min_password_length: The minimum length of the password all passwords with a length that is
                    smaller this will be invalid.

            :param test_threshold: The minimum number of tests the password must pass.
            :param password_tests: A list of tuples. The tuple contains the test and a reason for the user if the test
                    fails.
        """
        super().__init__()
        self.min_password_length = min_password_length
        self.test_threshold = test_threshold
        self.password_tests = password_tests

    def isInvalid(self, value):
        if not value:
            return False

        if len(value) < self.min_password_length:
            return self.tooShortMessage.translate(length=self.min_password_length)

        # Run our password test suite
        tests_errors = []
        tests_passed = 0
        for test, hint in self.password_tests:
            if re.match(test, value):
                tests_passed += 1
            else:
                tests_errors.append(str(hint))  # we may need to convert a "translate" object

        if tests_passed < self.test_threshold:
            return tests_errors

        return False

    def fromClient(self, skel: 'SkeletonInstance', name: str, data: dict) -> Union[None, List[ReadFromClientError]]:
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
        return False
