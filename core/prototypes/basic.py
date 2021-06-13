# -*- coding: utf-8 -*-
from viur.core import conf
from viur.core.skeleton import skeletonByKind


class BasicApplication(object):
	"""
	BasicApplication is a generic class serving as the base for the four BasicApplications.

	:ivar kindName: Name of the kind of data entities that are managed by the application. \
	This information is used to bind a specific :class:`server.skeleton.Skeleton`-class to the \
	application. For more information, refer to the function :func:`_resolveSkel`.
	:vartype kindName: str

	:ivar render: will be set to the appropriate render instance at runtime

	:ivar adminInfo: A ``dict`` holding the informations nessesary for the Vi/Admin to handle this module. If set to
		``None``, this module will be ignored by the frontend. The currently supported values are:

			name: ``str``
				Human-readable module name that will be shown in Vi/Admin

			handler: ``str`` (``list``, ``tree`` or ``singleton``):
				Which (proto-)type is used, to the frontend can
				initialize it handler correctly.

			icon: ``str``
				(Optional) The name (eg "icon-add") or a path relative the the project
				(eg. /static/icons/viur.svg) for the icon used in the UI for that module.

			columns: ``List[str]``
				(Optional) List of columns (bone names) that are displayed by default. Used only
				for the list handler.

			filter: ``Dict[str, str]``
				(Optional) Dictionary of additional parameters that will be send along when
				fetching entities from the server. Can be used to filter the entities being displayed  on the client-side.

			display: ``str`` ("default", "hidden" or "group")
				(Optional) "hidden" will hide the module in the main bar
				(itwill not be accessible directly, however it's registered with the frontend so it can be used in a
				relational bone). "group" will show this module in the main bar, but it will not be clickable.
				Clicking it will just try to expand it (assuming there are additional views defined).

			preview: ``Union[str, Dict[str, str]]``
				(Optional) A url that will be opened in a new tab and is expected to display
				the entity selected in the table. Can be “/{{module}}/view/{{key}}", with {{module}} and {{key}} getting
				replaced as needed. If more than one preview-url is needed, supply a dictionary where the key is
				the URL and the value the description shown to the user.

			views: ``List[Dict[str, Any]]``
				(Optional) List of nested adminInfo like dictionaries. Used to define
				additional views on the module. Useful f.e. for an order module, where you want separate list of
				"payed orders", "unpayed orders", "orders waiting for shipment", etc.  If such views are defined,
				the top-level entry in the menu bar will expand if clicked, revealing these additional filters.

			actions: ``List[str]``
				(Optional) List of actions supported by this modules. Actions can be defined by
				the frontend (like "add", "edit", "delete" or "preview"); it can be an action defined by a plugin
				loaded by the frontend; or it can be a so called "server side action" (see "customActions" below)

			customActions: ``List[str, dict]``
				(Optional) A mapping of names of server-defined actions that can be used
				in the ``actions`` list above to their definition dictionary. See .... for more details.

			sortIndex: ``int``
				(Optional) Defines the order in which the modules will appear in the main bar in
				ascrending order.

			indexedBones: ``List[str]``
				(Optional) List of bones, for which an (composite?) index exists in this
				view. This allows the fronted to signal the user that a given list can be sorted or filtered by this
				bone. If no additional filters are enforced by the :meth:`listFilter<viur.core.prototypes.list.listFilter>`
				and ``filter`` is not set, this should be all bones which are marked as indexed.

			changeInvalidates: ``List[str]``
				(Optional) A list of module-names which depend on the entities handled
				from this module. This allows the frontend to invalidate any caches in these depended modules if the
				data in this module changes. Example: This module may be a list-module handling the file_rootNode
				entities for the file module, so a edit/add/deletion action on this module should be reflected in the
			    rootNode-selector in the file-module itself. In this case, this property should be set to ``["file"]``.

			moduleGroup: ``str``
				(Optional) If set, should be a key of a moduleGroup defined in .... .

			editViews: ``Dict[str, Any]``
				(Optional) If set, will embed another list-widget in the edit forms for
				a given entity. See .... for more details.


		Test
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

		return skeletonByKind(self.kindName if self.kindName else str(type(self).__name__).lower())
