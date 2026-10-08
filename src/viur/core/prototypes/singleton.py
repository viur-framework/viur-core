import logging
import typing as t
from viur.core import current, utils, errors
from viur.core.decorators import *
from viur.core.cache import flushCache
from viur.core.skeleton import SkeletonInstance
from .skelmodule import SkelModule


class Singleton(SkelModule):
    """
    Singleton module prototype.

    It is used to store one single data entity, and needs to be sub-classed for individual modules.
    """
    handler = "singleton"
    accessRights = ("edit", "view", "manage")

    def getKey(self) -> str:
        """
        Returns the DB-Key for the current context.

        This implementation provides one module-global key.
        It *must* return *exactly one* key at any given time in any given context.

        :returns: Current context DB-key
        """
        return f"{self._resolveSkelCls().kindName}-modulekey"

    def viewSkel(self, *args, **kwargs) -> SkeletonInstance:
        """
        Retrieve a new instance of a :class:`viur.core.skeleton.Skeleton` that is used by the application
        for viewing the existing entry.

        The default is a Skeleton instance returned by :func:`~baseSkel`.

        .. seealso:: :func:`addSkel`, :func:`editSkel`, :func:`~baseSkel`

        :return: Returns a Skeleton instance for viewing the singleton entry.
        """
        return self.baseSkel(**kwargs)

    def editSkel(self, *args, **kwargs) -> SkeletonInstance:
        """
        Retrieve a new instance of a :class:`viur.core.skeleton.Skeleton` that is used by the application
        for editing the existing entry.

        The default is a Skeleton instance returned by :func:`~baseSkel`.

        .. seealso:: :func:`viewSkel`, :func:`editSkel`, :func:`~baseSkel`

        :return: Returns a Skeleton instance for editing the entry.
        """
        return self.baseSkel(**kwargs)

    ## External exposed functions

    @action
    def index(self):
        if not self.canIndex(None):
            raise errors.Unauthorized()

        return self.view()

    @action
    @skey
    def preview(self, *args, **kwargs) -> t.Any:
        """
        Renders data for the entry, without reading it from the database.
        This function allows to preview the entry without writing it to the database.

        Any entity values are provided via *kwargs*.

        The function uses the viewTemplate of the application.

        :returns: The rendered representation of the supplied data.
        """
        skel = self.viewSkel(allow_client_defined=utils.string.is_prefix(self.render.kind, "json"))
        if not self.canPreview(skel):
            raise errors.Unauthorized()

        skel.fromClient(kwargs)

        return self.render.view(skel)

    @action
    def structure(self, action: t.Optional[str] = "view") -> t.Any:
        """
            :returns: Returns the structure of our skeleton as used in list/view. Values are the defaultValues set
                in each bone.

            :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
        """
        # FIXME: In ViUR > 3.7 this could also become dynamic (ActionSkel paradigm).
        match action:
            case "view":
                skel = self.viewSkel()
                if not self.canView(skel):
                    raise errors.Unauthorized()

            case "edit":
                skel = self.editSkel()
                if not self.canEdit(skel):
                    raise errors.Unauthorized()

            case _:
                raise errors.NotImplemented(f"The action {action!r} is not implemented.")

        if not self.canStructure(skel):
            raise errors.Unauthorized()

        return self.render.render(f"structure.{action}", skel)

    @action
    def view(self, *args, **kwargs) -> t.Any:
        """
        Prepares and renders the singleton entry for viewing.

        The function performs several access control checks on the requested entity before it is rendered.

        .. seealso:: :func:`viewSkel`, :func:`canView`, :func:`onView`

        :returns: The rendered representation of the entity.

        :raises: :exc:`viur.core.errors.NotFound`, if there is no singleton entry existing, yet.
        :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
        """
        skel = self.viewSkel(allow_client_defined=utils.string.is_prefix(self.render.kind, "json"))
        if not self.canView(skel):
            raise errors.Unauthorized()

        key = self.getKey()  # The singleton's business key is its _id.

        if not skel.read(key):
            raise errors.NotFound()

        self.onView(skel)
        return self.render.view(skel)

    @action
    @force_ssl
    @skey(allow_empty=True)
    def edit(self, *, bounce: bool = False, **kwargs) -> t.Any:
        """
        Modify the existing entry, and render the entry, eventually with error notes on incorrect data.

        The entry is fetched by its entity key, which either is provided via *kwargs["key"]*,
        or as the first parameter in *args*. The function performs several access control checks
        on the singleton's entity before it is modified.

        .. seealso:: :func:`editSkel`, :func:`onEdit`, :func:`thenEdit`, :func:`canEdit`

        :returns: The rendered, edited object of the entry, eventually with error hints.

        :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
        :raises: :exc:`viur.core.errors.PreconditionFailed`, if the *skey* could not be verified.
        """
        skel = self.editSkel()
        if not self.canEdit(skel):
            raise errors.Unauthorized()

        key = self.getKey()  # The singleton's business key is its _id.
        if not skel.read(key):  # Its not there yet; we need to set the key again
            skel["key"] = key

        if (
            not kwargs  # no data supplied
            or not current.request.get().isPostRequest  # failure if not using POST-method
            or not skel.fromClient(kwargs, amend=True)  # failure on reading into the bones
            or bounce  # review before changing
        ):
            return self.render.edit(skel)

        self.onEdit(skel)
        skel.write()
        self.thenEdit(skel)
        return self.render.editSuccess(skel)

    def getContents(
        self,
        create: bool | dict | t.Callable[[SkeletonInstance], None] = False,
    ) -> SkeletonInstance | None:
        """
        Return the entity of this singleton application as :class:`SkeletonInstance` object.

        :param create: Whether the entity should be created if it does not exist.
            See :meth:`Skeleton.read` for more details.

        :returns: The read skeleton or `None`.
        """
        skel = self.viewSkel()
        key = self.getKey()  # The singleton's business key is its _id.

        if not skel.read(key, create=create):
            return None

        return skel

    def canIndex(self, skel: None) -> bool:
        """
        Access control function for :func:`index`.

        Allowed by default: index delegates to :func:`view`, whose own check applies.

        :param skel: Always None; index has no skeleton of its own.

        :returns: True, if the index may be used, False otherwise.
        """
        return True

    def canStructure(self, skel: SkeletonInstance) -> bool:
        """
        Access control function for :func:`structure`.

        Allowed by default: the structure of an action is checked by that action's own can-hook first.

        :param skel: The Skeleton whose structure is requested.

        :returns: True, if the structure may be retrieved, False otherwise.
        """
        return True

    def canPreview(self, skel: SkeletonInstance) -> bool:
        """
        Access control function for preview permission.

        Checks if the current user has the permission to preview the singletons entry.

        The default behavior is:
        - If no user is logged in, previewing is generally refused.
        - If the user has "root" access, previewing is generally allowed.
        - If the user has the modules "edit" permission (module-edit) enabled, \
        previewing is allowed.

        It should be overridden for a module-specific behavior.

        .. seealso:: :func:`preview`

        :param skel: The Skeleton of the entry that should be previewed.

        :returns: True, if previewing entries is allowed, False otherwise.
        """
        if not (user := current.user.get()):
            return False

        if user["access"] and "root" in user["access"]:
            return True

        if user["access"] and f"{self.moduleName}-edit" in user["access"]:
            return True

        return False

    def canEdit(self, skel: SkeletonInstance) -> bool:
        """
        Access control function for modification permission.

        Checks if the current user has the permission to edit the singletons entry.

        The default behavior is:
        - If no user is logged in, editing is generally refused.
        - If the user has "root" access, editing is generally allowed.
        - If the user has the modules "edit" permission (module-edit) enabled, editing is allowed.

        It should be overridden for a module-specific behavior.

        .. seealso:: :func:`edit`

        :param skel: The Skeleton of the entry that should be edited.

        :returns: True, if editing is allowed, False otherwise.
        """
        if not (user := current.user.get()):
            return False

        if user["access"] and "root" in user["access"]:
            return True

        if user["access"] and f"{self.moduleName}-edit" in user["access"]:
            return True

        return False

    def canView(self, skel: SkeletonInstance) -> bool:
        """
        Access control function for viewing permission.

        Checks if the current user has the permission to view the singletons entry.

        The default behavior is:
        - If no user is logged in, viewing is generally refused.
        - If the user has "root" access, viewing is generally allowed.
        - If the user has the modules "view" permission (module-view) enabled, viewing is allowed.

        It should be overridden for a module-specific behavior.

        .. seealso:: :func:`view`

        :param skel: The Skeleton of the entry that should be viewed.

        :returns: True, if viewing is allowed, False otherwise.
        """
        if not (user := current.user.get()):
            return False
        if user["access"] and "root" in user["access"]:
            return True
        if user["access"] and f"{self.moduleName}-view" in user["access"]:
            return True
        return False

    def onEdit(self, skel: SkeletonInstance):
        """
        Hook function that is called before editing an entry.

        It can be overridden for a module-specific behavior.

        :param skel: The Skeleton that is going to be edited.

        .. seealso:: :func:`edit`, :func:`thenEdit`
        """
        pass

    def thenEdit(self, skel: SkeletonInstance):
        """
        Hook function that is called after modifying the entry.

        It should be overridden for a module-specific behavior.
        The default is writing a log entry.

        :param skel: The Skeleton that has been modified.

        .. seealso:: :func:`edit`, :func:`onEdit`
        """
        logging.info(f"""Entry changed: {skel["key"]!r}""")
        flushCache(key=skel["key"])
        if user := current.user.get():
            logging.info(f"""User: {user["name"]!r} ({user["key"]!r})""")

    def onView(self, skel: SkeletonInstance):
        """
        Hook function that is called when viewing an entry.

        It should be overridden for a module-specific behavior.
        The default is doing nothing.

        :param skel: The Skeleton that is being viewed.

        .. seealso:: :func:`view`
        """
        pass


Singleton.json = True
