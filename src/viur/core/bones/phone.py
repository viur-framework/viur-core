import string
import re

from viur.core.bones.string import StringBone


class PhoneBone(StringBone):
    """
    The PhoneBone class is designed to store validated phone/fax numbers in configurable formats.

    This class provides an number validation method, ensuring that the given phone/fax number conforms to the
    required/configured format and structure.
    """
    type = "str.phone"
    """
    A string representing the type of the bone, in this case "str.phone".
    """
    def __init__(self, custom_regex=None):
        """
        Initializes the PhoneBone with an optional custom regex for phone number validation.

        :param str custom_regex: An optional custom regex pattern for phone number validation.
        """
        self.custom_regex = custom_regex or r'^\+?[1-9]\d{1,14}$'
        self.phone_regex = re.compile(self.custom_regex)

    def isInvalid(self, value):
        """
        Checks if the provided phone number is valid or not.

        :param str value: The phone number to be validated.
        :returns: An error message if the phone number is invalid or None if it is valid.
        :rtype: str, None

        The method checks if the provided phone number is valid according to the following criteria:

        1. The phone number must not be empty.
        2. The phone number must match the provided or default phone number format.
        """
        if not value:
            return "No value entered"
        
        if not self.phone_regex.match(value):
            return "Invalid phone number entered"
        
        return None
