import os
import yaml
import logging
from viur.core import Module, db
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
            for index in indexes:
                index["properties"] = [_property["name"] for _property in index["properties"]]
                indexes_dict.setdefault(index["kind"], []).append(index)

    except FileNotFoundError:
        logging.warning("index.yaml not found")
        return {}

    return indexes_dict


DATASTORE_INDEXES = __load_indexes_from_file()


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
        return self._resolveSkelCls(*args, **kwargs)()
