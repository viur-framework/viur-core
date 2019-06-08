# -*- coding: utf-8 -*-
from server.render.html.utils import jinjaGlobalFunction
from datetime import date as date_orig, time as time_orig, timedelta as timedelta_orig
from server.bones.dateBone import ExtendedDateTime as datetime_orig


@jinjaGlobalFunction
def dateTime(render):
	"""
	Jinja2 global: Returns the datetime class

	:return: datetime class
	:rtype: datetime
	"""
	return datetime_orig


@jinjaGlobalFunction
def date(render):
	"""
	Jinja2 global: Returns the date class

	:return: date class
	:rtype: date
	"""
	return date_orig


@jinjaGlobalFunction
def time(render):
	"""
	Jinja2 global: Returns the time class

	:return: time class
	:rtype: time
	"""
	return time_orig


@jinjaGlobalFunction
def timedelta(render):
	"""
	Jinja2 global: Returns the timedelta class

	:return: timedelta class
	:rtype: timedelta
	"""
	return timedelta_orig
