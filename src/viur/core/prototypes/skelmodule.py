import os
import yaml
import logging
from viur.core import Module, db, current, errors
from viur.core.decorators import *
from viur.core.config import conf
from viur.core.skeleton import skeletonByKind, Skeleton, SkeletonInstance
import typing as t


SINGLE_ORDER_TYPE = str | tuple[str, db.SortOrder]
"""
Type for exactly one sort order definitions.
"""

ORDER_TYPE = SINGLE_ORDER_TYPE | tuple[SINGLE_ORDER_TYPE] | list[SINGLE_ORDER_TYPE] | dict[str, str | int] | None
"""
Type for sort order definitions (any amount of single order definitions).
"""

DEFAULT_ORDER_TYPE = ORDER_TYPE | t.Callable[[db.Query], ORDER_TYPE]
"""
Type for default sort order definitions.
"""


def __load_indexes_from_file() -> dict[str, list]:
    """
        Loads all indexes from the index.yaml and stores it in a dictionary  sorted by the module(kind)
        :return A dictionary of indexes per module
    """
    indexes_dict = {}
    try:
        with open(os.path.join(conf.instance.project_base_path, "index.yaml"), "r") as file:
            indexes = yaml.safe_load(file)
            indexes = indexes.get("indexes", [])
            for index in indexes or ():
                index["properties"] = [_property["name"] for _property in index["properties"]]
                indexes_dict.setdefault(index["kind"], []).append(index)

    except FileNotFoundError:
        logging.warning("index.yaml not found")
        return {}

    return indexes_dict


DATASTORE_INDEXES = __load_indexes_from_file()

X_VIUR_BONELIST: t.Final[str] = "X-VIUR-BONELIST"
"""Defines the header parameter that might contain a client-defined bone list."""


class SkelModule(Module):
    """
        This is the extended module prototype used by any other ViUR module prototype.
        It a prototype which generally is bound to some database model abstracted by the ViUR skeleton system.
    """

    kindName: str = None
    """
        Name of the datastore kind that is handled by this module.

        This information is used to bind a specific :class:`viur.core.skeleton.Skeleton`-class to this
        prototype. By default, it is automatically determined from the module's class name, so a module named
        `Animal` refers to a Skeleton named `AnimalSkel` and its kindName is `animal`.

        For more information, refer to the function :func:`~_resolveSkelCls`.
    """

    default_order: DEFAULT_ORDER_TYPE = None
    """
    Allows to specify a default order for this module, which is applied when no other order is specified.

    Setting a default_order might result in the requirement of additional indexes, which are being raised
    and must be specified.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # automatically determine kindName when not set
        if self.kindName is None:
            self.kindName = str(type(self).__name__).lower()

        # assign index descriptions from index.yaml
        self.indexes = DATASTORE_INDEXES.get(self.kindName, [])

    def _resolveSkelCls(self, *args, **kwargs) -> t.Type[Skeleton]:
        """
        Retrieve the generally associated :class:`viur.core.skeleton.Skeleton` that is used by
        the application.

        This is either be defined by the member variable *kindName* or by a Skeleton named like the
        application class in lower-case order.

        If this behavior is not wanted, it can be definitely overridden by defining module-specific
        :func:`~viewSkel`, :func:`~addSkel`, or :func:`~editSkel` functions, or by overriding this
        function in general.

        :return: Returns a Skeleton class that matches the application.
        """
        return skeletonByKind(self.kindName)

    def baseSkel(self, *args, **kwargs) -> SkeletonInstance:
        """
        Returns an instance of an unmodified base skeleton for this module.

        This function should only be used in cases where a full, unmodified skeleton of the module is required, e.g.
        for administrative or maintenance purposes.

        By default, baseSkel is used by :func:`~viewSkel`, :func:`~addSkel`, and :func:`~editSkel`.
        """
        return self.skel(**kwargs)

    def skel(
        self,
        *,
        allow_client_defined: bool = False,
        bones: tuple[str, ...] | t.List[str] = (),
        exclude_bones: tuple[str, ...] | t.List[str] = (),
        **kwargs,
    ) -> SkeletonInstance:
        """
        Retrieve module-specific skeleton, optionally as subskel.

        :param allow_client_defined: Evaluates header X-VIUR-BONELIST to contain a comma-separated list of bones.
            Using this parameter enforces that the Skeleton class has a subskel named "*" for required bones that
            must exist.
        :param bones: Allows to specify a list of bones to form a subskel.
        :param exclude_bones: Provide a list of bones which are always excluded.

        The parameters `bones` and `allow_client_defined` can be combined.
        """
        skel_cls = self._resolveSkelCls(**kwargs)
        bones = set(bones) if bones else set()

        if allow_client_defined:
            # if bonelist := current.request.get().kwargs.get(X_VIUR_BONELIST.lower()):  # DEBUG
            if bonelist := current.request.get().request.headers.get(X_VIUR_BONELIST):
                if "*" not in skel_cls.subSkels:  # a named star-subskel "*"" must exist!
                    raise errors.BadRequest(f"Use of {X_VIUR_BONELIST!r} requires a defined star-subskel")

                bones |= {bone.strip() for bone in bonelist.split(",")}
            else:
                allow_client_defined = False  # is not client-defined!

        bones.difference_update(exclude_bones)

        # Return a subskel?
        if bones:
            # When coming from outside of a request, "*" is always involved.
            if allow_client_defined:
                current.request.get().response.vary = (X_VIUR_BONELIST, *(current.request.get().response.vary or ()))
                return skel_cls.subskel("*", bones=bones)

            return skel_cls(bones=bones)

        elif exclude_bones:
            # Return full skel, without generally excluded bones
            bones.update(skel_cls.__boneMap__.keys())
            bones.difference_update(exclude_bones)
            return skel_cls(bones=bones)

        # Otherwise, return full skeleton
        return skel_cls()

    def _apply_default_order(self, query: db.Query):
        """
        Apply the setting from `default_order` to a given db.Query.

        The `default_order` will only be applied when the query has no other order, or is on a multquery.
        """

        # Apply default_order when possible!
        if (
                self.default_order
                and query.queries
                and not isinstance(query.queries, list)
                and not query.queries.orders
                and not current.request.get().kwargs.get("search")
        ):
            if callable(default_order := self.default_order):
                default_order = default_order(query)

            if isinstance(default_order, dict):
                logging.debug(f"Applying filter {default_order=}")
                query.mergeExternalFilter(default_order)

            elif default_order:
                logging.debug(f"Applying {default_order=}")

                # FIXME: This ugly test can be removed when there is type that abstracts SortOrders
                if (
                    isinstance(default_order, str)
                    or (
                        isinstance(default_order, tuple)
                        and len(default_order) == 2
                        and isinstance(default_order[0], str)
                        and isinstance(default_order[1], db.SortOrder)
                    )
                ):
                    query.order(default_order)
                else:
                    query.order(*default_order)

    @force_ssl
    @force_post
    @exposed
    @skey
    @access("root")
    def add_or_edit(self, key: db.Key | int | str, **kwargs) -> t.Any:
        """
        This function is intended to be used by importers.
        Only "root"-users are allowed to use it.
        """

        # Adjust key
        db_key = db.key_helper(key, target_kind=self.kindName, adjust_kind=True)

        # Retrieve and verify existing entry
        db_entity = db.get(db_key)
        is_add = not bool(db_entity)

        # Instanciate relevant skeleton
        if is_add:
            skel = self.addSkel()
        else:
            skel = self.editSkel()
            skel.dbEntity = db_entity  # assign existing entity

        skel["key"] = db_key

        if (
            not kwargs  # no data supplied
            or not skel.fromClient(kwargs)  # failure on reading into the bones
        ):
            # render the skeleton in the version it could as far as it could be read.
            return self.render.render("add_or_edit", skel)

        if is_add:
            self.onAdd(skel)
        else:
            self.onEdit(skel)

        skel.write()

        if is_add:
            self.onAdded(skel)
            return self.render.addSuccess(skel)

        self.onEdited(skel)
        return self.render.editSuccess(skel)
