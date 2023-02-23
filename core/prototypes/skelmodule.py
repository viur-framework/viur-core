from viur.core import Module
from viur.core.skeleton import skeletonByKind, Skeleton, SkeletonInstance
from viur.core import conf
from typing import Tuple, Type


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

    accessRights: Tuple[str] = None
    """
        If set, a tuple of access rights (like add, edit, delete) that this module supports.

        These will be prefixed on instance startup with the actual module name (becoming file-add, file-edit etc)
        and registered in ``conf["viur.accessRights"]`` so these will be available on the access bone in user/add
        or user/edit.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.handler and self.accessRights:
            for r in self.accessRights:
                rightName = "%s-%s" % (self.moduleName, r)

                if rightName not in conf["viur.accessRights"]:
                    conf["viur.accessRights"].append(rightName)

    def _resolveSkelCls(self, *args, **kwargs) -> Type[Skeleton]:
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
        return skeletonByKind(self.kindName if self.kindName else str(type(self).__name__).lower())

    def baseSkel(self, *args, **kwargs) -> SkeletonInstance:
        """
        Returns an instance of an unmodified base skeleton for this module.

        This function should only be used in cases where a full, unmodified skeleton of the module is required, e.g.
        for administrative or maintenance purposes.

        By default, baseSkel is used by :func:`~viewSkel`, :func:`~addSkel`, and :func:`~editSkel`.
        """
        return self._resolveSkelCls(*args, **kwargs)()
