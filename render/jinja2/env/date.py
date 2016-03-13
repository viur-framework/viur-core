# -*- coding: utf-8 -*-
from server.render.jinja2.utils import jinjaGlobal
from datetime import datetime as datetime_orig, date as date_orig, time as time_orig, timedelta as timedelta_orig

@jinjaGlobal
def dateTime(render):
	"""
	Jinja2 global: Returns the datetime class

	:return: datetime class
	:rtype: datetime
	"""
	return datetime_orig

@jinjaGlobal
def date(render):
	"""
	Jinja2 global: Returns the date class

	:return: date class
	:rtype: date
	"""
	return date_orig

@jinjaGlobal
def time(render):
	"""
	Jinja2 global: Returns the time class

	:return: time class
	:rtype: time
	"""
	return time_orig


@jinjaGlobal
def timedelta(render):
	"""
	Jinja2 global: Returns the timedelta class

	:return: timedelta class
	:rtype: timedelta
	"""
	return timedelta_orig

