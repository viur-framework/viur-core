# -*- coding: utf-8 -*-

__jinjaGlobals_ = {}
__jinjaFilters_ = {}
__jinjaExtensions_ = []

def getGlobals():
	return __jinjaGlobals_

def getFilters():
	return __jinjaFilters_

def getExtensions():
	return __jinjaExtensions_


def jinjaGlobal(f):
	"""
	Decorator, marks a function as a Jinja2 global.
	"""
	__jinjaGlobals_[f.__name__] = f

def jinjaFilter(f):
	"""
	Decorator, marks a function as a Jinja2 filter.
	"""
	__jinjaFilters_[f.__name__] = f

def jinjaExtension(ext):
	"""
	Function for activating extensions in Jinja2.
	"""
	if ext not in __jinjaExtensions_:
		__jinjaExtensions_.append(ext)

