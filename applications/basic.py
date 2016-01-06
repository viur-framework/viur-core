#-*- coding: utf-8 -*-
from server import conf
from server.skeleton import Skeleton, skeletonByKind

class BasicApplication(object):
	"""
	BasicApplication is a generic ViUR BasicApplication.

	:ivar kindName: Name of the kind of data entities that are managed by the application. \
	This information is used to bind a specific :class:`server.skeleton.Skeleton`-class to the \
	application. For more information, refer to the function :func:`resolveSkel`.
	:vartype kindName: str
	"""

	kindName = None # The generic kindname for this module.
	adminInfo = None
	accessRights = None

	def __init__(self, modulName, modulPath, *args, **kwargs):
		self.modulName = modulName
		self.modulPath = modulPath

		if self.adminInfo and self.accessRights:
			for r in self.accessRights:
				rightName = "%s-%s" % (modulName, r)

				if not rightName in conf["viur.accessRights"]:
					conf["viur.accessRights"].append(rightName)

	def _resolveSkel(self, *args, **kwargs):
		"""
		Retrieve the generally associated :class:`server.skeleton.Skeleton` that is used by
		the application.

		This is either be defined by the member variable *kindName* or by a Skeleton named like the
		application class in lower-case order.

		If this behavior is not wanted, it can be definitely overridden by defining module-specific
		:func:`viewSkel`,:func:`addSkel`, or :func:`editSkel` functions, or by overriding this
		function in general.

		:return: Returns a Skeleton instance that matches the application.
		:rtype: server.skeleton.Skeleton
		"""

		if self.kindName:
			kName = self.kindName
		else:
			kName = unicode(type(self).__name__).lower()

		return skeletonByKind( kName )()
