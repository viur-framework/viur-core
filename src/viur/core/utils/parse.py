"""
ViUR utility functions regarding parsing.
"""
import typing as t
import datetime


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


def timedelta(value: datetime.timedelta | int | float | str) -> datetime.timedelta:
    """
    Parse a value into a timedelta object.

    This method takes a seconds value and converts it into
    a timedelta object, if it is not already one.
    :param value: The value to be parsed into a timedelta.
    :returns: A timedelta object.
    """
    if isinstance(value, datetime.timedelta):
        return value
    if isinstance(value, str):
        value = float(value)
    return datetime.timedelta(seconds=value)
