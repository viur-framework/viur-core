"""
ViUR utility functions regarding parsing.
"""
import typing as t


def bool(value: t.Any, truthy_values: t.Iterable[str] = ("true", "yes", "1")) -> bool:
    """
    Parse a value into a boolean based on accepted truthy values.

    This method takes a value, converts it to a lowercase string,
    removes whitespace, and checks if it matches any of the provided
    truthy values.
    :param value: The value to be parsed into a boolean.
    :param truthy_values: An iterable of strings representing truthy values.
        Default is ("true", "yes", "1").
    :returns: True if the value matches any of the truthy values, False otherwise.
    """
    return str(value).strip().lower() in truthy_values
