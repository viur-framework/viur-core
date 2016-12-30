# -*- coding: utf-8 -*-
from server import conf
from server.skeleton import skeletonByKind


class BasicApplication(object):
	"""
	BasicApplication is a generic class serving as the base for the four BasicApplications.

	:ivar kindName: Name of the kind of data entities that are managed by the application. \
	This information is used to bind a specific :class:`server.skeleton.Skeleton`-class to the \
	application. For more information, refer to the function :func:`_resolveSkel`.
	:vartype kindName: str

	:ivar render: will be set to the appropriate render instance like html json or admin/vi renderer on runtime
	"""

	kindName = None  # The generic kindname for this module.

	adminInfo = None
	accessRights = None

	def __init__(self, moduleName, modulePath, *args, **kwargs):
		self.moduleName = moduleName
		self.modulePath = modulePath
		self.render = None

		if self.adminInfo and self.accessRights:
			for r in self.accessRights:
				rightName = "%s-%s" % (moduleName, r)

				if not rightName in conf["viur.accessRights"]:
					conf["viur.accessRights"].append(rightName)

	def _resolveSkelCls(self, *args, **kwargs):
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

		return skeletonByKind(self.kindName if self.kindName else unicode(type(self).__name__).lower())
