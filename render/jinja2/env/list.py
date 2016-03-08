# -*- coding: utf-8 -*-
from server.render.jinja2.utils import jinjaGlobal, jinjaFilter

@jinjaFilter
def sortList(render, l, sortField, keyField="key", reverse=False):
	"""
	Jinja2 filter: Sorts a list containing dict entries by a field.

	:param l: The list to be sorted.
	:type l: list of dict

	:param reverse: If True, reverses the sorting order.
	:type reverse: bool

	:return: The sorted list of dict.
	:rtype: list of dict
	"""
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
