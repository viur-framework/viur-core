import re
import typing as t

from viur.core import i18n
from viur.core.bones.string import StringBone
from viur.core.bones.base import ReadFromClientError, ReadFromClientErrorSeverity

DEFAULT_REGEX = r"^\+?(\d{1,3})[-\s]?(\d{1,4})[-\s]?(\d{1,4})[-\s]?(\d{1,9})$"


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
        *,
        test: t.Optional[t.Pattern[str]] = DEFAULT_REGEX,
        max_length: int = 15,  # maximum allowed numbers according to ITU-T E.164
        default_country_code: t.Optional[str] = None,
        **kwargs: t.Any,
    ) -> None:
        """
        Initializes the PhoneBone with an optional custom regex for phone number validation, a default country code,
        and a flag to apply the default country code if none is provided.

        :param test: An optional custom regex pattern for phone number validation.
        :param max_length: The maximum length of the phone number. Passed to "StringBone".
        :param default_country_code: The default country code to apply (with leading +) for example "+49"
        If None is provided the PhoneBone will ignore auto prefixing of the country code.
        :param kwargs: Additional keyword arguments. Passed to "StringBone".
        :raises ValueError: If the default country code is not in the correct format for example "+123".
        """
        if default_country_code and not re.match(r"^\+\d{1,3}$", default_country_code):
            raise ValueError(f"Invalid default country code format: {default_country_code}")

        self.test: t.Pattern[str] = re.compile(test) if isinstance(test, str) else test
        self.default_country_code: t.Optional[str] = default_country_code
        super().__init__(max_length=max_length, **kwargs)

    @staticmethod
    def _extract_digits(value: str) -> str:
        """
        Extracts and returns only the digits from the given value.

        :param value: The input string from which to extract digits.
        :return: A string containing only the digits from the input value.
        """
        return re.sub(r"[^\d+]", "", value)

    def isInvalid(self, value: str) -> t.Optional[str]:
        """
        Checks if the provided phone number is valid or not.

        :param value: The phone number to be validated.
        :return: An error message if the phone number is invalid or None if it is valid.

        The method checks if the provided phone number is valid according to the following criteria:
        1. The phone number must not be empty.
        2. The phone number must match the provided or default phone number format.
        3. The phone number cannot exceed 15 digits, or the specified maximum length if provided (digits only).
        """
        if not value:
            return i18n.translate("core.bones.error.novalueentered", "No value entered")

        if self.test and not self.test.match(value):
            return i18n.translate("core.bones.error.invalidphone", "Invalid phone number entered")

        # make sure max_length is not exceeded.
        if is_invalid := super().isInvalid(self._extract_digits(value)):
            return is_invalid

        return None

    def singleValueFromClient(
        self, value: str, skel: t.Any, bone_name: str, client_data: t.Any
    ) -> t.Tuple[t.Optional[str], t.Optional[t.List[ReadFromClientError]]]:
        """
        Processes a single value from the client, applying the default country code if necessary and validating the
        phone number.

        :param value: The phone number provided by the client.
        :param skel: Skeleton data (not used in this method).
        :param bone_name: The name of the bone (not used in this method).
        :param client_data: Additional client data (not used in this method).
        :return: A tuple containing the processed phone number and an optional list of errors.
        """
        value = value.strip()

        # Replace country code starting with 00 with +
        if value.startswith("00"):
            value = "+" + value[2:]

        # Apply default country code if none is provided and default_country_code is set
        if self.default_country_code and value[0] != "+":
            if value.startswith("0"):
                value = value[1:]  # Remove leading 0 from city code
            value = f"{self.default_country_code} {value}"

        if err := self.isInvalid(value):
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

        return value, None

    def structure(self) -> t.Dict[str, t.Any]:
        """
        Returns the structure of the PhoneBone, including the test regex pattern.

        :return: A dictionary representing the structure of the PhoneBone.
        """
        return super().structure() | {
            "test": self.test.pattern if self.test else "",
            "default_country_code": self.default_country_code,
        }
