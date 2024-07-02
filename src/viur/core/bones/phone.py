import re
from typing import Optional, Pattern, Tuple, List, Any

from viur.core.bones.string import StringBone
from viur.core.bones.base import ReadFromClientError, ReadFromClientErrorSeverity


class PhoneBone(StringBone):
    """
    The PhoneBone class is designed to store validated phone/fax numbers in configurable formats.
    This class provides a number validation method, ensuring that the given phone/fax number conforms to the
    required/configured format and structure.
    """
    type: str = "str.phone"
    """
    A string representing the type of the bone, in this case "str.phone".
    """

    def __init__(
        self,
        custom_regex: Optional[Pattern] = None,
        default_country_code: str = "+49",
        apply_default_country_code: bool = False,
        **kwargs: Any
    ) -> None:
        """
        Initializes the PhoneBone with an optional custom regex for phone number validation, a default country code,
        and a flag to apply the default country code if none is provided.
        :param custom_regex: An optional custom regex pattern for phone number validation.
        :param default_country_code: The default country code to apply if none is provided.
        :param apply_default_country_code: Whether to apply the default country code if none is provided.
        """
        self.custom_regex: Pattern = custom_regex or re.compile(
            r'^(?:\+|00)?[1-9]\d{0,2}[-\s]?\d{1,4}[-\s]?\d{1,4}[-\s]?\d{1,4}$|'
            r'^(0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{1,4})$'
        )
        self.phone_regex: Pattern = (
            re.compile(self.custom_regex) if isinstance(self.custom_regex, str) else self.custom_regex
        )
        self.default_country_code: str = default_country_code
        self.apply_default_country_code: bool = apply_default_country_code

        super().__init__(**kwargs)

    def isInvalid(self, value: str) -> Optional[str]:
        """
        Checks if the provided phone number is valid or not.
        :param value: The phone number to be validated.
        :returns: An error message if the phone number is invalid or None if it is valid.
        :rtype: Optional[str]
        The method checks if the provided phone number is valid according to the following criteria:
        1. The phone number must not be empty.
        2. The phone number must match the provided or default phone number format.
        3. If the phone number has no country code and apply_default_country_code is True,
        the default country code is applied.
        """
        if not value:
            return "No value entered"

        if not self.phone_regex.match(value):
            return "Invalid phone number entered"

        return None

    def singleValueFromClient(
        self, value: str, skel: Any, bone_name: str, client_data: Any
    ) -> Tuple[Optional[str], Optional[List[Any]]]:
        """
        Processes a single value from the client, applying the default country code if necessary and validating the
        phone number.
        :param value: The phone number provided by the client.
        :param skel: Skeleton data (not used in this method).
        :param bone_name: The name of the bone (not used in this method).
        :param client_data: Additional client data (not used in this method).
        :returns: A tuple containing the processed phone number and an optional list of errors.
        :rtype: Tuple[Optional[str], Optional[List[Any]]]
        """
        # Apply default country code if none is provided and apply_default_country_code is True
        if self.apply_default_country_code and not value.startswith(('+', '00')):
            if value.startswith('0'):
                value = value[1:]  # Remove leading 0 from city code
            value = self.default_country_code + value

        err = self.isInvalid(value)
        if err:
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

        return value, None

    def structure(self) -> dict:
        return super().structure() | {
            "phone_regex": self.phone_regex.pattern if self.phone_regex else ""
        }
