import re
import string
from encodings import idna
from viur.core.bones.string import StringBone
from viur.core import i18n

_DNS_LABEL_RE = re.compile(r"(?!-)[a-z0-9-]{1,63}(?<!-)", re.IGNORECASE)
"""A single DNS label per RFC 1035: 1-63 alphanumerics or hyphens, no leading or trailing hyphen."""

_LOCAL_PART_CHARS = frozenset(string.ascii_letters + string.digits + "!#$%&'*+-/=?^_`{|}~")
"""Characters allowed in an unquoted local part (RFC 5321 dot-atom); the dot is only valid as a separator."""

_UNICODE_LOWER_BOUND = chr(0x80)
"""Local-part characters from this codepoint (U+0080) upwards are accepted as non-ASCII (SMTPUTF8)."""


class EmailBone(StringBone):
    """
    The EmailBone class is a designed to store syntactically validated email addresses.

    This class provides an email validation method, ensuring that the given email address conforms to the
    required format and structure.
    """
    type = "str.email"
    """
    A string representing the type of the bone, in this case "str.email".
    """

    def isInvalid(self, value: str) -> str | None:
        """
        Checks if the provided email address is valid or not.

        :param value: The email address to be validated.
        :returns: An error message if the email address is invalid or None if it is valid.

        The address must satisfy all of the following:

        1. It must not be empty and must be shorter than 256 characters.
        2. It must contain exactly one "@", separating the local part (account) and the domain.
        3. The local part must be a valid RFC 5321 dot-atom (see :meth:`_is_valid_local_part`).
        4. The domain must be a sequence of valid IDNA-encoded labels (see :meth:`_is_valid_domain`).
        """
        if not value:
            return i18n.translate("core.bones.error.novalueentered", "No value entered")

        if not self._is_valid_address(value):
            return i18n.translate("core.bones.error.invalidemail", "Invalid email entered")

        return None

    @classmethod
    def _is_valid_address(cls, value: str) -> bool:
        """Validate the overall structure and delegate to the local-part and domain checks."""
        if len(value) >= 256 or value.count("@") != 1:
            return False
        account, _, domain = value.partition("@")
        return cls._is_valid_local_part(account) and cls._is_valid_domain(domain)

    @staticmethod
    def _is_valid_local_part(account: str) -> bool:
        """
        Validate the local part (before the "@") as an RFC 5321 dot-atom.

        It must be 1-64 characters long, must not start or end with a dot and must not contain
        consecutive dots. Besides the allowed ASCII atom characters, Unicode characters from
        U+0080 upwards are accepted (SMTPUTF8).
        """
        if not account or len(account) > 64:
            return False
        if account.startswith(".") or account.endswith(".") or ".." in account:
            return False
        return all(
            char == "." or char in _LOCAL_PART_CHARS or char >= _UNICODE_LOWER_BOUND
            for char in account
        )

    @staticmethod
    def _is_valid_domain(domain: str) -> bool:
        """
        Validate the domain (after the "@") as a sequence of IDNA-encoded RFC 1035 labels.

        There must be at least two labels and the TLD must not be purely numeric (which rejects
        bare IP addresses). Each label is IDNA-encoded and then matched against ``_DNS_LABEL_RE``,
        which also rejects a leading or trailing hyphen and enforces the 63-character label limit.
        """
        labels = domain.split(".")
        if len(labels) < 2 or labels[-1].isdigit():
            return False
        for label in labels:
            try:
                ascii_label = idna.ToASCII(label).decode("ascii")
            except Exception:
                return False
            if not _DNS_LABEL_RE.fullmatch(ascii_label):
                return False
        return True
