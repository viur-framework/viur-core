import copy
import inspect
import types
import typing as t
import logging
from viur.core import db, errors, current, utils
from viur.core.config import conf


class Method:
    """
    Abstraction wrapper for any public available method.
    """

    @classmethod
    def ensure(cls, func: t.Callable | "Method") -> "Method":
        """
        Ensures the provided `func` parameter is either a Method already, or turns it
        into a Method. This is done to avoid stacking Method objects, which may create
        unwanted results.
        """
        if isinstance(func, Method):
            return func

        return cls(func)

    def __init__(self, func: t.Callable):
        # Content
        self._func = func
        self.__name__ = func.__name__
        self._instance = None

        # Attributes
        self.exposed = None  # None = unexposed, True = exposed, False = internal exposed
        self.ssl = False
        self.methods = ("GET", "POST", "HEAD")
        self.seo_language_map = None

        # Inspection
        self.signature = inspect.signature(self._func)

        # Guards
        self.skey = None
        self.access = None

    def __get__(self, obj, objtype=None):
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
        Calls the method with given args and kwargs.

        Prepares and filters argument values from args and kwargs regarding self._func's signature and type annotations,
        if present.

        Method objects normally wrap functions which are externally exposed. Therefore, any arguments passed from the
        client are str-values, and are automatically parsed when equipped with type-annotations.

        This preparation of arguments therefore inspects the target function as follows
        - incoming values are parsed to their particular type, if type annotations are present
        - parameters in *args and **kwargs are being checked against their signature; only relevant values are being
            passed, anything else is thrown away.
        - execution of guard configurations from @skey and @access, if present
        """

        if trace := conf.debug.trace:
            logging.debug(f"calling {self._func=} with raw {args=}, {kwargs=}")

        def parse_value_by_annotation(annotation: type, name: str, value: str | list | tuple) -> t.Any:
            """
            Tries to parse a value according to a given type.
            May be called recursively to handle unions, lists and tuples as well.
            """
            # simple types
            if annotation is str:
                return str(value)
            elif annotation is int:
                return int(value)
            elif annotation is float:
                return float(value)
            elif annotation is bool:
                return utils.parse.bool(value)
            elif annotation is types.NoneType:
                return None

            # complex types
            origin_type = t.get_origin(annotation)

            if origin_type is list and len(annotation.__args__) == 1:
                if not isinstance(value, list):
                    value = [value]

                return [parse_value_by_annotation(annotation.__args__[0], name, item) for item in value]

            elif origin_type is tuple and len(annotation.__args__) == 1:
                if not isinstance(value, tuple):
                    value = (value, )

                return tuple(parse_value_by_annotation(annotation.__args__[0], name, item) for item in value)

            elif origin_type is t.Literal:
                if not any(value == str(literal) for literal in annotation.__args__):
                    raise errors.NotAcceptable(f"Expecting any of {annotation.__args__} for {name}")

                return value

            elif origin_type is t.Union or isinstance(annotation, types.UnionType):
                for i, sub_annotation in enumerate(annotation.__args__):
                    try:
                        return parse_value_by_annotation(sub_annotation, name, value)
                    except ValueError:
                        if i == len(annotation.__args__) - 1:
                            raise

            elif annotation is db.Key:
                if isinstance(value, db.Key):
                    return value

                return parse_value_by_annotation(int | str, name, value)

            raise errors.NotAcceptable(f"Unhandled type {annotation=} for {name}={value!r}")

        # examine parameters
        args_iter = iter(args)

        parsed_args = []
        parsed_kwargs = {}
        varargs = []
        varkwargs = False

        for i, (param_name, param) in enumerate(self.signature.parameters.items()):
            if self._instance and i == 0 and param_name == "self":
                continue

            param_type = param.annotation if param.annotation is not param.empty else None
            param_required = param.default is param.empty

            # take positional parameters first
            if param.kind in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.POSITIONAL_ONLY
            ):
                try:
                    value = next(args_iter)

                    if param_type:
                        value = parse_value_by_annotation(param_type, param_name, value)

                    parsed_args.append(value)
                    continue
                except StopIteration:
                    pass

            # otherwise take kwargs or variadics
            if (
                param.kind in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY
                )
                and param_name in kwargs
            ):
                value = kwargs.pop(param_name)

                if param_type:
                    value = parse_value_by_annotation(param_type, param_name, value)

                parsed_kwargs[param_name] = value

            elif param.kind == inspect.Parameter.VAR_POSITIONAL:
                varargs = list(args_iter)
            elif param.kind == inspect.Parameter.VAR_KEYWORD:
                varkwargs = True
            elif param_required:
                if self.skey and param_name == self.skey["forward_payload"]:
                    continue

                raise errors.NotAcceptable(f"Missing required parameter {param_name!r}")

        # Here's a short clarification on the variables used here:
        #
        # - parsed_args     = tuple of (the type-parsed) arguments that have been assigned based on the signature
        # - parsed_kwargs   = dict of (the type-parsed) keyword arguments that have been assigned based on the signature
        # - args            = either parsed_args, or parsed_args + remaining args if the function accepts *args
        # - kwargs          = either parsed_kwars, or parsed_kwargs | remaining kwargs if the function accepts **kwargs
        # - varargs         = indicator that the args also contain variable args (*args)
        # - varkwards       = indicator that variable kwargs (**kwargs) are also contained in the kwargs
        #

        # Extend args to any varargs, and redefine args
        args = tuple(parsed_args + varargs)

        # always take "skey"-parameter name, when configured, as parsed_kwargs
        if self.skey and self.skey["name"] in kwargs:
            parsed_kwargs[self.skey["name"]] = kwargs.pop(self.skey["name"])

        # When varkwargs are accepted, merge parsed_kwargs and kwargs, otherwise just use parsed_kwargs
        if varkwargs := varkwargs and bool(kwargs):
            kwargs = parsed_kwargs | kwargs
        else:
            kwargs = parsed_kwargs

        # Trace message for final call configuration
        if trace := conf.debug.trace:
            logging.debug(f"calling {self._func=} with cleaned {args=}, {kwargs=}")

        # evaluate skey guard setting?
        if self.skey and not current.request.get().skey_checked:  # skey guardiance is only required once per request
            if trace:
                logging.debug(f"@skey {self.skey=}")

            security_key = kwargs.pop(self.skey["name"], "")

            # validation is necessary?
            if allow_empty := self.skey["allow_empty"]:
                # allow_empty can be callable, to detect programmatically
                if callable(allow_empty):
                    required = not allow_empty(args, kwargs)
                # or allow_empty can be a sequence of allowed keys
                elif isinstance(allow_empty, (list, tuple)):
                    required = any(k for k in kwargs.keys() if k not in allow_empty)
                # otherwise, varargs or varkwargs may not be empty.
                else:
                    required = varargs or varkwargs or security_key
                    if trace:
                        logging.debug(f"@skey {required=} because either {varargs=} or {varkwargs=} or {security_key=}")
            else:
                required = True

            if required:
                if trace:
                    logging.debug(f"@skey wanted, validating {security_key!r}")

                from viur.core import securitykey
                payload = securitykey.validate(security_key, **self.skey["extra_kwargs"])
                current.request.get().skey_checked = True

                if not payload or (self.skey["validate"] and not self.skey["validate"](payload)):
                    raise errors.PreconditionFailed(
                        self.skey["message"] or f"Missing or invalid parameter {self.skey['name']!r}"
                    )

                if self.skey["forward_payload"]:
                    kwargs |= {self.skey["forward_payload"]: payload}

        # evaluate access guard setting?
        if self.access:
            user = current.user.get()

            if trace := conf.debug.trace:
                logging.debug(f"@access {user=} {self.access=}")

            if not user:
                if offer_login := self.access["offer_login"]:
                    raise errors.Redirect(offer_login if isinstance(offer_login, str) else "/user/login")

                raise errors.Unauthorized(self.access["message"]) if self.access["message"] else errors.Unauthorized()

            ok = "root" in user["access"]

            if not ok and self.access["access"]:
                for acc in self.access["access"]:
                    if trace:
                        logging.debug(f"@access checking {acc=}")

                    # Callable directly tests access
                    if callable(acc):
                        if acc():
                            ok = True
                            break

                        continue

                    # Otherwise, check for access rights
                    if isinstance(acc, str):
                        acc = (acc, )

                    assert isinstance(acc, (tuple, list, set))

                    if all(a in user["access"] for a in acc):
                        ok = True
                        break

            if trace:
                logging.debug(f"@access {ok=}")

            if not ok:
                raise errors.Forbidden(self.access["message"]) if self.access["message"] else errors.Forbidden()

        # call with instance when provided
        if self._instance:
            return self._func(self._instance, *args, **kwargs)

        return self._func(*args, **kwargs)

    def describe(self) -> dict:
        """
        Describes the Method with a
        """
        return_doc = t.get_type_hints(self._func).get("return")

        ret = {
            "args": {
                param.name: {
                    "type": str(param.annotation) if param.annotation is not inspect.Parameter.empty else None,
                    "default": str(param.default) if param.default is not inspect.Parameter.empty else None,
                }
                for param in self.signature.parameters.values()
            },
            "returns": str(return_doc).strip() if return_doc else None,
            "accepts": self.methods,
            "docs": self._func.__doc__.strip() if self._func.__doc__ else None,
            "aliases": tuple(self.seo_language_map.keys()) if self.seo_language_map else None,
        }

        if self.skey:
            ret["skey"] = self.skey["name"]

        if self.access:
            ret["access"] = [str(access) for access in self.access["access"]]  # must be a list to be JSON-serializable

        return ret

    def register(self, target: dict, name: str, language: str | None = None):
        """
        Registers the Method under `name` and eventually some customized SEO-name for the provided language
        """
        if self.exposed is None:
            return

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

    handler: str | t.Callable = None
    """
    This is the module's handler, respectively its type.
    Use the @property-decorator in specific Modules to construct the handler's value dynamically.
    A module without a handler setting cannot be described, so cannot be handled by admin-tools.
    """

    accessRights: tuple[str] = None
    """
    If set, a tuple of access rights (like add, edit, delete) that this module supports.

    These will be prefixed on instance startup with the actual module name (becoming file-add, file-edit etc)
    and registered in ``conf.user.access_rights`` so these will be available on the access bone in user/add
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

    adminInfo: dict[str, t.Any] | t.Callable = None
    """
        This is a ``dict`` holding the information necessary for the Vi/Admin to handle this module.

            name: ``str``
                Human-readable module name that will be shown in the admin tool.

            handler: ``str`` (``list``, ``tree`` or ``singleton``):
                Allows to override the handler provided by the module. Set this only when *really* necessary,
                otherwise it can be left out and is automatically injected by the Module's prototype.

            icon: ``str``
                (Optional) Either the Shoelace icon library name or a path relative to the project's deploy folder
                (e.g. /static/icons/viur.svg) for the icon used in the admin tool for this module.

            columns: ``List[str]``
                (Optional) List of columns (bone names) that are displayed by default.
                Used only by the List handler.

            filter: ``Dict[str, str]``
                (Optional) Dictionary of additional parameters that will be send along when
                fetching entities from the server. Can be used to filter the entities being displayed on the
                client-side.

            display: ``str`` ("default", "hidden" or "group")
                (Optional) "hidden" will hide the module in the admin tool's main bar.
                (itwill not be accessible directly, however it's registered with the frontend so it can be used in a
                relational bone). "group" will show this module in the main bar, but it will not be clickable.
                Clicking it will just try to expand it (assuming there are additional views defined).

            preview: ``Union[str, Dict[str, str]]``
                (Optional) A url that will be opened in a new tab and is expected to display
                the entity selected in the table. Can be “/{{module}}/view/{{key}}", with {{module}} and {{key}} getting
                replaced as needed. If more than one preview-url is needed, supply a dictionary where the key is
                the URL and the value the description shown to the user.

            views: ``List[Dict[str, t.Any]]``
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
                bone. If no additional filters are enforced by the
                :meth:`listFilter<viur.core.prototypes.list.listFilter>` and ``filter`` is not set, this should be
                all bones which are marked as indexed.

            changeInvalidates: ``List[str]``
                (Optional) A list of module-names which depend on the entities handled
                from this module. This allows the frontend to invalidate any caches in these depended modules if the
                data in this module changes. Example: This module may be a list-module handling the file_rootNode
                entities for the file module, so a edit/add/deletion action on this module should be reflected in the
                rootNode-selector in the file-module itself. In this case, this property should be set to ``["file"]``.

            moduleGroup: ``str``
                (Optional) If set, should be a key of a moduleGroup defined in .... .

            editViews: ``Dict[str, t.Any]``
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

                # fixme: Turn conf.user.access_rights into a set.
                if right not in conf.user.access_rights:
                    conf.user.access_rights.append(right)

        # Collect methods and (sub)modules
        self._methods = {}
        self._modules = {}
        self._update_methods()

    def _update_methods(self):
        """
        Internal function to update methods and submodules.
        This function should only be called when member attributes are dynamically modified by the module.
        """
        self._methods.clear()
        self._modules.clear()

        for key in dir(self):
            if key[0] == "_":
                continue
            if isinstance(getattr(self.__class__, key, None), property):
                continue

            prop = getattr(self, key)

            if isinstance(prop, Method):
                self._methods[key] = prop
            elif isinstance(prop, Module):
                self._modules[key] = prop

    def describe(self) -> dict | None:
        """
        Meta description of this module.
        """
        # Use cached description?
        if isinstance(self._cached_description, dict):
            return self._cached_description

        # Retrieve handler
        if not (handler := self.handler):
            return None

        # Default description
        ret = {
            "name": self.__class__.__name__,
            "handler": ".".join((handler, self.__class__.__name__.lower())),
            "methods": {
                name: method.describe() for name, method in self._methods.items()
            },
        }

        # Extend indexes, if available
        # todo: This must be handled by SkelModule
        if indexes := getattr(self, "indexes", None):
            ret["indexes"] = indexes

        # Merge adminInfo if present
        if admin_info := self.adminInfo() if callable(self.adminInfo) else self.adminInfo:
            assert isinstance(admin_info, dict), \
                f"adminInfo can either be a dict or a callable returning a dict, but got {type(admin_info)}"
            ret |= admin_info

        # Cache description for later re-use.
        if self._cached_description is not False:
            self._cached_description = ret

        return ret

    def register(self, target: dict, render: object):
        """
        Registers this module's public functions to a given resolver.
        This function is executed on start-up, and can be sub-classed.
        """
        # connect instance to render
        self.render = render

        # Map module under SEO-mapped name, if available.
        if self.seo_language_map:
            for lang in conf.i18n.available_languages or [conf.i18n.default_language]:
                # Map the module under each translation
                if translated_module_name := self.seo_language_map.get(lang):
                    translated_module = target.setdefault(translated_module_name, {})

                    # Map module methods to the previously determined target
                    for name, method in self._methods.items():
                        method.register(translated_module, name, lang)

            conf.i18n.language_module_map[self.moduleName] = self.seo_language_map

        # Map the module also under it's original name
        if self.moduleName != "index":
            target = target.setdefault(self.moduleName, {})

        # Map module methods to the previously determined target
        for name, method in self._methods.items():
            method.register(target, name)

        # Register sub modules
        for name, module in self._modules.items():
            module.register(target, self.render)
