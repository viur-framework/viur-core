from viur.core.bones.string import StringBone
from encodings import idna
import string


class EmailBone(StringBone):
    type = "str.email"

    def isInvalid(self, value):
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
