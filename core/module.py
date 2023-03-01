from typing import Dict, Any, Union, Callable


class Module:
    """
        This is the root module prototype that serves a minimal module in the ViUR system without any other bindings.
    """

    handler: Union[str, Callable] = None
    """
    This is the module's handler, respectively its type.
    It can be provided as a callable() which determines the handler at runtime.
    A module without a handler setting is invalid.
    """

    adminInfo: Union[Dict[str, Any], Callable] = None
    """
        This is a ``dict`` holding the information necessary for the Vi/Admin to handle this module.

            name: ``str``
                Human-readable module name that will be shown in Vi/Admin

            handler: ``str`` (``list``, ``tree`` or ``singleton``):
                Allows to override the handler provided by the module. Set this only when *really* necessary.

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

            customActions: ``Dict[str, dict]``
                (Optional) A mapping of names of server-defined actions that can be used
                in the ``actions`` list above to their definition dictionary. See .... for more details.

            disabledActions: ``List[str, dict]``
                (Optional) A list of disabled actions. The frontend will inject default actions like add or edit
                even if they're not listed in actions. Listing them here will prevent that. It's up to the frontend
                to decide if that action won't be visible at all or it's button just being disabled.

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

            If this is a function, it must take no parameters and return the dictionary as shown above. This
            can be used to customize the appearance of the Vi/Admin to individual users.
    """

    def __init__(self, moduleName: str, modulePath: str, *args, **kwargs):
        self.render = None  # will be set to the appropriate render instance at runtime
        self._cached_description = None  # caching used by describe()
        self.moduleName = moduleName  # Name of this module (usually it's class name, e.g. "file")
        self.modulePath = modulePath  # Path to this module in URL-routing (e.g. "json/file")

    def describe(self) -> Union[Dict, None]:
        """
        Meta description of this module.
        """
        # Use cached description?
        if isinstance(self._cached_description, dict):
            return self._cached_description

        # Retrieve handler
        if not (handler := self.handler() if callable(self.handler) else self.handler):
            return None

        # Default description
        ret = {
            "name": self.__class__.__name__,
            "handler": ".".join((handler, self.__class__.__name__.lower())),
        }

        # Extend indexes, if available
        if indexes := getattr(self, "indexes", None):
            ret["indexes"] = indexes

        # Merge adminInfo if present
        if admin_info := self.adminInfo() if callable(self.adminInfo) else self.adminInfo:
            assert isinstance(admin_info, dict), \
                f"adminInfo can either be a dict or a callable returning a dict, but got {type(admin_info)}"
            ret |= admin_info

        # Cache description for later re-use.
        self._cached_description = ret

        return ret
