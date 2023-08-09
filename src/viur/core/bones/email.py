import string
from encodings import idna

from viur.core.bones.string import StringBone


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

    def isInvalid(self, value):
        """
        Checks if the provided email address is valid or not.

        :param str value: The email address to be validated.
        :returns: An error message if the email address is invalid or None if it is valid.
        :rtype: str, None

        The method checks if the provided email address is valid according to the following criteria:

        1. The email address must not be empty.
        2. The email address must be shorter than 256 characters.
        3. The local part (account) must be shorter than or equal to 64 characters.
        4. The email address must contain an "@" symbol, separating the local part (account) and the domain part.
        5. The domain part must be a valid IDNA-encoded string and should not contain any spaces.
        6. The local part (account) should only contain valid characters.
        7. The local part (account) can also contain Unicode characters within the range of U+0080 to U+10FFFF.
        """
        if not value:
            return "No value entered"
        try:
            assert len(value) < 256
            account, domain = value.split(u"@")
            subDomain, tld = domain.rsplit(".", 1)
            assert account and subDomain and tld
            assert subDomain[0] != "."
            assert len(account) <= 64
        except:
            return "Invalid email entered"
        isValid = True
        validChars = string.ascii_letters + string.digits + "!#$%&'*+-/=?^_`{|}~."
        unicodeLowerBound = u"\u0080"
        unicodeUpperBound = u"\U0010FFFF"
        for char in account:
            if not (char in validChars or (char >= unicodeLowerBound and char <= unicodeUpperBound)):
                isValid = False
        try:
            idna.ToASCII(subDomain)
            idna.ToASCII(tld)
        except:
            isValid = False
        if " " in subDomain or " " in tld:
            isValid = False
        if isValid:
            return None
        else:
            return "Invalid email entered"
