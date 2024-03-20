"""
The PasswordBone class is a specialized version of the StringBone class designed to handle password
data. It hashes the password data before saving it to the database and prevents it from being read
directly. The class also includes various tests to determine the strength of the entered password.
"""
import hashlib
import re
import typing as t
from viur.core import conf, utils
from viur.core.bones.string import StringBone
from viur.core.i18n import translate
from .base import ReadFromClientError, ReadFromClientErrorSeverity

# https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#pbkdf2
PBKDF2_DEFAULT_ITERATIONS = 600_000


def encode_password(password: str | bytes, salt: str | bytes,
                    iterations: int = PBKDF2_DEFAULT_ITERATIONS, dklen: int = 42
                    ) -> dict[str, str | bytes]:
    """Decodes a pashword and return the hash and meta information as hash"""
    password = password[:conf.user.max_password_length]
    if isinstance(password, str):
        password = password.encode()
    if isinstance(salt, str):
        salt = salt.encode()
    pwhash = hashlib.pbkdf2_hmac("sha256", password, salt, iterations, dklen)
    return {
        "pwhash": pwhash.hex().encode(),
        "salt": salt,
        "iterations": iterations,
        "dklen": dklen,
    }


class PasswordBone(StringBone):
    """
    A specialized subclass of the StringBone class designed to handle password data.

    The PasswordBone hashes the password before saving it to the database and prevents it from
    being read directly. It also includes various tests to determine the strength of the entered
    password.
    """
    type = "password"
    """A string representing the bone type, which is "password" in this case."""
    saltLength = 13

    tests: t.Iterable[t.Iterable[t.Tuple[str, str, bool]]] = (
        (r"^.*[A-Z].*$", translate("core.bones.password.no_capital_letters",
                                   defaultText="The password entered has no capital letters."), False),
        (r"^.*[a-z].*$", translate("core.bones.password.no_lowercase_letters",
                                   defaultText="The password entered has no lowercase letters."), False),
        (r"^.*\d.*$", translate("core.bones.password.no_digits",
                                defaultText="The password entered has no digits."), False),
        (r"^.*\W.*$", translate("core.bones.password.no_special_characters",
                                defaultText="The password entered has no special characters."), False),
        (r"^.{8,}$", translate("core.bones.password.too_short",
                               defaultText="The password is too short. It requires for at least 8 characters."), True),
    )
    """Provides tests based on regular expressions to test the password strength.

    Note: The provided regular expressions have to produce exactly the same results in Python and JavaScript.
          This requires that some feature either cannot be used, or must be rewritten to match on both engines.
    """

    def __init__(
        self,
        *,
        descr: str = "Password",
        test_threshold: int = 4,
        tests: t.Iterable[t.Iterable[t.Tuple[str, str, bool]]] = tests,
        **kwargs
    ):
        """
            Initializes a new PasswordBone.

            :param test_threshold: The minimum number of tests the password must pass.
            :param password_tests: Defines separate tests specified as tuples of regex, hint and required-flag.
        """
        super().__init__(descr=descr, **kwargs)
        self.test_threshold = test_threshold
        if tests is not None:
            self.tests = tests

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

        # Run our password test suite
        tests_errors = []
        tests_passed = 0
        required_test_failed = False

        for test, hint, required in self.tests:
            if re.match(test, value):
                tests_passed += 1
            else:
                tests_errors.append(str(hint))  # we may need to convert a "translate" object
                if required:  # we have a required test that failed make sure we abort
                    required_test_failed = True

        if tests_passed < self.test_threshold or required_test_failed:
            return tests_errors

        return False

    def fromClient(self, skel: 'SkeletonInstance', name: str, data: dict) -> None | list[ReadFromClientError]:
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
        if name not in data:
            return [ReadFromClientError(ReadFromClientErrorSeverity.NotSet, "Field not submitted")]

        if not (value := data[name]):
            # PasswordBone is special: As it cannot be read, don't set back to None if no value is given
            # This means a password once set can only be changed - but not deleted.
            return [ReadFromClientError(ReadFromClientErrorSeverity.Empty, "No value entered")]

        if err := self.isInvalid(value):
            return [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

        # As we don't escape passwords and allow most special characters we'll hash it early on so we don't open
        # an XSS attack vector if a password is echoed back to the client (which should not happen)
        skel[name] = encode_password(value, utils.string.random(self.saltLength))

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
        if not (value := skel.accessedValues.get(name)):
            return False

        if isinstance(value, dict):  # It is a pre-hashed value (probably fromClient)
            skel.dbEntity[name] = value
        else:  # This has been set by skel["password"] = "secret", we'll still have to hash it
            skel.dbEntity[name] = encode_password(value, utils.string.random(self.saltLength))

        # Ensure our indexed flag is up2date
        indexed = self.indexed and parentIndexed

        if indexed and name in skel.dbEntity.exclude_from_indexes:
            skel.dbEntity.exclude_from_indexes.discard(name)
        elif not indexed and name not in skel.dbEntity.exclude_from_indexes:
            skel.dbEntity.exclude_from_indexes.add(name)

        return True

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

    def structure(self) -> dict:
        return super().structure() | {
            "tests": self.tests if self.test_threshold else (),
            "test_threshold": self.test_threshold,
        }
