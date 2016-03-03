# -*- coding: utf-8 -*-
from server.render.jinja2.utils import jinjaGlobal, jinjaFilter
import random

@jinjaGlobal
def randomList(render, start = 0, end = 0, amount = 0):
	"""
	Jinja2 global: Generates a randomized list of integers.

	:param start: Value to start with
	:type start: int

	:param end: Value to end at.
	:type end: int

	:param amount: Number of sampling.
	:type amount: int

	:return: Generated list of integers.
	:rtype: list of int
	"""

	return random.sample(range(start, end), amount)

@jinjaFilter
def sortList(render, l, sortField, keyField="key", reverse=False):
	"""
	Jinja2 filter: Sorts a list containng dict entries by a field.

	:param l: The list to be sorted.
	:type l: list of dict

	:param reverse: If True, reverses the sorting order.
	:type reverse: bool

	:return: The sorted list of dict.
	:rtype: list of dict
	"""
	assert isList(render, l, ofDict=True)

	fields = sortField.split(".")
	sortedItems = {}

	for i in l:
		entry = i

		for sortField in fields:
			entry = entry.get(sortField)
			if entry is None:
				break

			#if entry[0] is string and entry is list
			if (isinstance(entry, list)
			    and len(entry) > 0
			    and isinstance(entry[0], basestring)):
				entry = sorted(entry)[0]

		sortedItems.update({i[keyField]: entry})

	sortedItems = sorted(sortedItems.iteritems(), key=lambda (k,v): (v,k), reverse=reverse)

	sortedList = []
	for key, value in sortedItems.items():
		for i in l:
			if key == i[keyField]:
				sortedList.append(i) #neu zusammen bauen

	return sortedList

@jinjaFilter
def shuffleList(render, l, amount=0):
	"""
	Jinja2 filter: Shuffles a list.
	Optionally returns the first ``amount`` items.

	:param l: The list to be shuffled.
	:type l: list

	:param amount: The amount of items to be returned. If 0 or omitted, the entire list is returned.
	:type amount: int

	:return: The shuffled list.
	:rtype: list
	"""
	random.shuffle(l)

	if amount > 0:
		return l[:amount]

	return l

@jinjaFilter
def listAttr(render, l, attrName):
	"""
	Jinja2 filter: Returns a list of fields from a list of dict, e. g. a list of keys.

	:param l: List of dict

	:param attrName:
	:return:
	"""
	assert isList(render, l, ofDict=True)
	attrList = []

	for i in l:
		if attrName in i.keys():
			attrList.append(str(i[attrName]))
		elif "dest" in i and attrName in i["dest"].keys():
			attrList.append(str(i["dest"][attrName]))

	return attrList

@jinjaFilter
def isList(render, l, ofDict = False):
	"""
	Jinja2 filter: Checks if an object is a list.

	:param l: The list to be checked.
	:type l: any

	:param ofDict: If ``l`` is a list, check if it consists of dict items.
	:type ofDict: bool

	:return: True if all requirements are met.
	:rtype: bool
	"""
	if isinstance(l, list):
		if ofDict:
			return all(isinstance(x, dict) for x in l)

		return True

	return False
