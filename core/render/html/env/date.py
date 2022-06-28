from typing import Type

from datetime import date as date_orig, datetime as datetime_orig, time as time_orig, timedelta as timedelta_orig

from ..utils import jinjaGlobalFunction
from ..default import Render


@jinjaGlobalFunction
def dateTime(render: Render) -> Type[datetime_orig]:
    """
    Jinja2 global: Returns the datetime class

    :return: datetime class
    """
    return datetime_orig


@jinjaGlobalFunction
def date(render: Render) -> Type[date_orig]:
    """
    Jinja2 global: Returns the date class

    :return: date class
    """
    return date_orig


@jinjaGlobalFunction
def time(render: Render) -> Type[time_orig]:
    """
    Jinja2 global: Returns the time class

    :return: time class
    """
    return time_orig


@jinjaGlobalFunction
def timedelta(render: Render) -> Type[timedelta_orig]:
    """
    Jinja2 global: Returns the timedelta class

    :return: timedelta class
    """
    return timedelta_orig
