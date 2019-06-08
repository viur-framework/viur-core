# -*- coding: utf-8 -*-
import html.parser, string


class htmlSerializer(html.parser.HTMLParser):
	valid_tags = ('font', 'b', 'a', 'i', 'u', 'span', 'div', 'img', 'ul', 'li', 'acronym', 'h1', 'h2',
				  'h3')  # FIXME: tags und tag-valdierungs-klassen
	from html.entities import entitydefs

	def __init__(self):
		html.parser.HTMLParser.__init__(self)
		self.result = ""
		self.endTagList = []
		self.remove_all = False

	def handle_data(self, data):
		if data:
			self.result += data

	def handle_charref(self, name):
		self.result += "&#%s;" % (name)

	def handle_entityref(self, name):
		if name in self.entitydefs:
			self.result += "&%s;" % (name)

	def handle_starttag(self, tag, attrs):
		""" Delete all tags except for legal ones """
		if tag in self.valid_tags and not self.remove_all:
			self.result = self.result + '<' + tag
			for k, v in attrs:
				if string.lower(k[0:2]) != 'on' and string.lower(v[0:10]) != 'javascript':
					self.result = '%s %s="%s"' % (self.result, k, v)
			endTag = '</%s>' % tag
			self.endTagList.insert(0, endTag)
			self.result = self.result + '>'

	def handle_endtag(self, tag):
		if tag in self.valid_tags and not self.remove_all:
			self.result = "%s</%s>" % (self.result, tag)
			remTag = '</%s>' % tag
			self.endTagList.remove(remTag)
		elif tag == "p":
			self.result += "<br />"

	def cleanup(self):  # FIXME: vertauschte tags
		""" Append missing closing tags """
		for j in range(len(self.endTagList)):
			self.result = self.result + self.endTagList[j]

	def santinize(self, instr, remove_all=False):
		html.parser.HTMLParser.__init__(self)
		instr = instr.replace("\r\n", "\n").replace("<br>\n", "\n").replace("<br />\n", "\n").replace("<br>",
																									  "\n").replace(
			"<br />", "\n")
		self.result = ""
		self.endTagList = []
		self.remove_all = remove_all
		self.feed(instr)
		self.close()
		self.cleanup()
		if remove_all:
			return (self.result)
		else:
			return (self.result.replace("\n", "<br />\n"))
