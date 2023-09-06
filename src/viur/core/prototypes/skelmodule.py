from viur.core import db, conf, Module
from viur.core.skeleton import skeletonByKind, Skeleton, SkeletonInstance
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

    def skel(self, action: str | None = None, *args, **kwargs) -> SkeletonInstance:
        """
        Requests an instance to a skeleton that is bound to this SkelModule.

        The requested skeleton can be specific to an action specified by action.
        This can be a SkeletonInstance returned by a specific `actionSkel`-function, like `addSkel` for an
        "add"-operation, or the skel-function is sub-classed by the module to return a customized, other skeleton.

        :param action: Optional parameter to request a modified skeleton for a specific "action".
        """
        if action:
            for postfix in ("Skel", "_skel"):
                if skel_func := getattr(self, f"{action}{postfix}", None):
                    return skel_func(*args, **kwargs)

        return self._resolveSkelCls(*args, **kwargs)()

    def read(
        self,
        key: db.Key | str | int,
        action: str = None,
        *args, **kwargs
    ) -> SkeletonInstance | None:
        """
        Reads and returns a SkeletonInstance to a given key.

        :param key: Key of the entry to be read.
        :param action: Action parameter for :func:`~skel`

        Returns None when no entry for the given key was found.
        """
        skel = self.skel(action)
        if skel.fromDB(key):
            return skel

        return None

    def can(self, action: str) -> bool:
        if (user := current.user.get()) and user["access"]:
            return "root" in user["access"] or f"{self.moduleName}-{action}" in user["access"]:

        return False
