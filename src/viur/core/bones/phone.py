import re
from typing import Optional, Pattern, Tuple, List, Any, Dict

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
        custom_regex: Optional[Pattern[str]] = None,
        max_length: int = 15,
        default_country_code: str = "+49",
        apply_default_country_code: bool = False,
        **kwargs: Any
    ) -> None:
        """
        Initializes the PhoneBone with an optional custom regex for phone number validation, a default country code,
        and a flag to apply the default country code if none is provided.

        Args:
            custom_regex (Optional[Pattern[str]]): An optional custom regex pattern for phone number validation.
            max_length (int): The maximum length of the phone number.
            default_country_code (str): The default country code to apply if none is provided.
            apply_default_country_code (bool): Whether to apply the default country code if none is provided.
            **kwargs (Any): Additional keyword arguments.
        """
        self.custom_regex: Pattern[str] = custom_regex or re.compile(
            r'^(?:\+|00)?[1-9]\d{0,2}[-\s]?\d{1,4}[-\s]?\d{1,4}[-\s]?\d{1,4}$|'
            r'^(0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{1,4})$'
        )
        self.phone_regex: Pattern[str] = (
            re.compile(self.custom_regex) if isinstance(self.custom_regex, str) else self.custom_regex
        )
        self.default_country_code: str = default_country_code
        self.apply_default_country_code: bool = apply_default_country_code

        super().__init__(max_length=max_length, **kwargs)

    def isInvalid(self, value: str) -> Optional[str]:
        """
        Checks if the provided phone number is valid or not.

        Args:
            value (str): The phone number to be validated.

        Returns:
            Optional[str]: An error message if the phone number is invalid or None if it is valid.

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

        is_invalid: Optional[str] = super().isInvalid(value)

        if is_invalid:
            return is_invalid
        return None

    def singleValueFromClient(
        self, value: str, skel: Any, bone_name: str, client_data: Any
    ) -> Tuple[Optional[str], Optional[List[ReadFromClientError]]]:
        """
        Processes a single value from the client, applying the default country code if necessary and validating the
        phone number.

        Args:
            value (str): The phone number provided by the client.
            skel (Any): Skeleton data (not used in this method).
            bone_name (str): The name of the bone (not used in this method).
            client_data (Any): Additional client data (not used in this method).

        Returns:
            Tuple[Optional[str], Optional[List[ReadFromClientError]]]: 
            A tuple containing the processed phone number and an optional list of errors.
        """
        # Apply default country code if none is provided and apply_default_country_code is True
        if self.apply_default_country_code and not value.startswith(('+', '00')):
            if value.startswith('0'):
                value = value[1:]  # Remove leading 0 from city code
            value = self.default_country_code + value

        err: Optional[str] = self.isInvalid(value)
        if err:
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

        return value, None

    def structure(self) -> Dict[str, Any]:
        """
        Returns the structure of the PhoneBone, including the phone regex pattern.

        Returns:
            Dict[str, Any]: A dictionary representing the structure of the PhoneBone.
        """
        return super().structure() | {
            "phone_regex": self.phone_regex.pattern if self.phone_regex else ""
        }
    