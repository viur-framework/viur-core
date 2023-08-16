import copy
import inspect
from typing import Any, Callable, get_type_hints
from viur.core.config import conf


class Method:
    """
    Abstraction wrapper for any public available method.
    """

    @classmethod
    def ensure(cls, func):
        """
        Ensures the provided func is either a Method already, or turns it into a Method.
        This is done to avoid stacking Method objects, which may create unwanted results.
        """
        if isinstance(func, Method):
            return func

        return cls(func)

    def __init__(self, func: Callable):
        self.internal = False
        self.ssl = False
        self.skey = None
        self.methods = ("GET", "POST", "HEAD")
        self.seo_language_map = None

        self._func = func
        self._instance = None

    def __get__(self, obj, objtype):
        """
        This binds the Method to an object.

        To do it, the Method instance is copied and equipped with the individual _instance member.
        """
        if obj:
            bound = copy.copy(self)
            bound._instance = obj
            return bound

        return self

    def __call__(self, *args, **kwargs):
        """
        Wrapper to call the Method directly.
        """
        if self.skey:
            self.skey(*args, **kwargs)

        # call with instance when provided
        if self._instance:
            return self._func(self._instance, *args, **kwargs)

        return self._func(*args, **kwargs)

    def register(self, target: dict, name: str, language: str | None = None):
        """
        Registers the Method under `name` and eventually some customized SEO-name for the provided language
        """
        target[name] = self

        # reassign for SEO mapping as well
        if self.seo_language_map:
            for lang in tuple(self.seo_language_map.keys()) if not language else (language, ):
                if translated_name := self.seo_language_map.get(lang):
                    target[translated_name] = self


class Module:
    """
    This is the root module prototype that serves a minimal module in the ViUR system without any other bindings.
    """

    handler: str | Callable = None
    """
    This is the module's handler, respectively its type.
    It can be provided as a callable() which determines the handler at runtime.
    A module without a handler setting is invalid.
    """

    accessRights: tuple[str] = None
    """
    If set, a tuple of access rights (like add, edit, delete) that this module supports.

    These will be prefixed on instance startup with the actual module name (becoming file-add, file-edit etc)
    and registered in ``conf["viur.accessRights"]`` so these will be available on the access bone in user/add
    or user/edit.
    """

    roles: dict = {}
    r"""
    Allows to specify role settings for a module.

    Defaults to no role definition, which ignores the module entirely in the role-system.
    In this case, access rights can still be set individually on the user's access bone.

    A "*" wildcard can either be used as key or as value to allow for "all roles", or "all rights".

        .. code-block:: python

            # Example
            roles = {
                "*": "view",                # Any role may only "view"
                "editor": ("add", "edit"),  # Role "editor" may "add" or "edit", but not "delete"
                "admin": "*",               # Role "admin" can do everything
            }

    """

    seo_language_map: dict[str: str] = {}
    r"""
    The module name is the first part of a URL.
    SEO-identifiers have to be set as class-attribute ``seoLanguageMap`` of type ``dict[str, str]`` in the module.
    It maps a *language* to the according *identifier*.

    .. code-block:: python
        :name: module seo-map
        :caption: modules/myorders.py
        :emphasize-lines: 4-7

        from viur.core.prototypes import List

        class MyOrders(List):
            seo_language_map = {
                "de": "bestellungen",
                "en": "orders",
            }

    By default the module would be available under */myorders*, the lowercase module name.
    With the defined :attr:`seoLanguageMap`, it will become available as */de/bestellungen* and */en/orders*.

    Great, this part is now user and robot friendly :)
    """

    adminInfo: dict[str, Any] | Callable = None
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

        if self.handler and self.accessRights:
            for right in self.accessRights:
                right = f"{self.moduleName}-{right}"

                # fixme: Turn conf["viur.accessRights"] into a set.
                if right not in conf["viur.accessRights"]:
                    conf["viur.accessRights"].append(right)

    def describe(self) -> dict | None:
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

        '''
        func = inspect.getmembers(self, predicate=inspect.ismethod)
        filtered_funcs = []
        for fn in func:
            if not fn:
                continue
            f = fn[1]

            viur_flags = getattr(f, "viur_flags", {})

            attributes = {
                "exposed": viur_flags.get("exposed", False),
                "method": viur_flags.get("method", []),
                "skey": "skey" in viur_flags
            }

            if attributes["exposed"]:
                _params = {}
                signature = inspect.signature(f)

                annotations = get_type_hints(f)

                for parameter in signature.parameters.values():
                    _params[parameter.name] = {
                        "type": "-",
                        "default": None,
                    }

                    if parameter.annotation is not inspect.Parameter.empty:
                        _params[parameter.name]["type"] = str(parameter.annotation)

                    if parameter.default is not inspect.Parameter.empty:
                        _params[parameter.name]["default"] = str(parameter.default)

                return_hint = annotations.get("return")
                attributes |= {
                    "name": f.__name__,
                    "docs": f.__doc__,
                    "args": _params,
                    "return": "-" if return_hint is None else str(return_hint)
                }

                attributes.pop("exposed")

                filtered_funcs.append(attributes)

        ret["functions"] = filtered_funcs
        '''

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

    def register(self, target: dict, render: object):
        """
        Registers this module's public functions to a given resolver.
        This function is executed on start-up, and can be sub-classed.
        """
        # connect instance to render
        self.render = render

        # todo: This should be held elsewhere, and not determined all the time...
        functions = {}
        modules = {}

        for key in dir(self):
            if key[0] == "_":
                continue

            prop = getattr(self, key)

            if isinstance(prop, Method):
                functions[key] = prop
            elif isinstance(prop, Module):
                modules[key] = prop

        # Map module under SEO-mapped name, if available.
        for lang in conf["viur.availableLanguages"] or [conf["viur.defaultLanguage"]]:
            # Map the module under each translation
            if translated_module_name := self.seo_language_map.get(lang):
                translated_module = target.setdefault(translated_module_name, {})

                # Map module functions to the previously determined target
                for name, func in functions.items():
                    func.register(translated_module, name, lang)

        # Map the module also under it's original name
        if self.moduleName != "index":
            target = target.setdefault(self.moduleName, {})

        # Map module functions to the previously determined target
        for name, func in functions.items():
            func.register(target, name)

        # Register sub modules
        for name, module in modules.items():
            module.register(target, self.render)
