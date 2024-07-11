import logging
import typing as t
from viur.core import db, current, utils, errors
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
        return f"{self.editSkel().kindName}-modulekey"

    def viewSkel(self, *args, **kwargs) -> SkeletonInstance:
        """
        Retrieve a new instance of a :class:`viur.core.skeleton.Skeleton` that is used by the application
        for viewing the existing entry.

        The default is a Skeleton instance returned by :func:`~baseSkel`.

        .. seealso:: :func:`addSkel`, :func:`editSkel`, :func:`~baseSkel`

        :return: Returns a Skeleton instance for viewing the singleton entry.
        """
        return self.baseSkel(*args, **kwargs)

    def editSkel(self, *args, **kwargs) -> SkeletonInstance:
        """
        Retrieve a new instance of a :class:`viur.core.skeleton.Skeleton` that is used by the application
        for editing the existing entry.

        The default is a Skeleton instance returned by :func:`~baseSkel`.

        .. seealso:: :func:`viewSkel`, :func:`editSkel`, :func:`~baseSkel`

        :return: Returns a Skeleton instance for editing the entry.
        """
        return self.baseSkel(*args, **kwargs)

    ## External exposed functions

    @exposed
    @skey
    def preview(self, *args, **kwargs) -> t.Any:
        """
        Renders data for the entry, without reading it from the database.
        This function allows to preview the entry without writing it to the database.

        Any entity values are provided via *kwargs*.

        The function uses the viewTemplate of the application.

        :returns: The rendered representation of the supplied data.
        """
        if not self.canPreview():
            raise errors.Unauthorized()

        skel = self.viewSkel()
        skel.fromClient(kwargs)

        return self.render.view(skel)

    @exposed
    def structure(self, *args, **kwargs) -> t.Any:
        """
        :returns: Returns the structure of our skeleton as used in list/view. Values are the defaultValues set
            in each bone.

        :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
        """
        skel = self.viewSkel()
        if not self.canView():
            raise errors.Unauthorized()
        return self.render.view(skel)

    @exposed
    def view(self, *args, **kwargs) -> t.Any:
        """
        Prepares and renders the singleton entry for viewing.

        The function performs several access control checks on the requested entity before it is rendered.

        .. seealso:: :func:`viewSkel`, :func:`canView`, :func:`onView`

        :returns: The rendered representation of the entity.

        :raises: :exc:`viur.core.errors.NotFound`, if there is no singleton entry existing, yet.
        :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
        """

        skel = self.viewSkel()
        if not self.canView():
            raise errors.Unauthorized()

        key = db.Key(self.editSkel().kindName, self.getKey())

        if not skel.fromDB(key):
            raise errors.NotFound()

        self.onView(skel)
        return self.render.view(skel)

    @exposed
    @force_ssl
    @skey(allow_empty=True)
    def edit(self, *args, **kwargs) -> t.Any:
        """
        Modify the existing entry, and render the entry, eventually with error notes on incorrect data.

        The entry is fetched by its entity key, which either is provided via *kwargs["key"]*,
        or as the first parameter in *args*. The function performs several access control checks
        on the singleton's entity before it is modified.

        .. seealso:: :func:`editSkel`, :func:`onEdited`, :func:`canEdit`

        :returns: The rendered, edited object of the entry, eventually with error hints.

        :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
        :raises: :exc:`viur.core.errors.PreconditionFailed`, if the *skey* could not be verified.
        """
        if not self.canEdit():
            raise errors.Unauthorized()

        key = db.Key(self.editSkel().kindName, self.getKey())
        skel = self.editSkel()
        if not skel.fromDB(key):  # Its not there yet; we need to set the key again
            skel["key"] = key

        if (
            not kwargs  # no data supplied
            or not current.request.get().isPostRequest  # failure if not using POST-method
            or not skel.fromClient(kwargs, amend=True)  # failure on reading into the bones
            or utils.parse.bool(kwargs.get("bounce"))  # review before changing
        ):
            return self.render.edit(skel)

        self.onEdit(skel)
        skel.toDB()
        self.onEdited(skel)
        return self.render.editSuccess(skel)

    def getContents(self) -> SkeletonInstance | None:
        """
        Returns the entity of this singleton application as :class:`viur.core.skeleton.Skeleton` object.

        :returns: The content as Skeleton provided by :func:`viewSkel`.
        """
        skel = self.viewSkel()
        key = db.Key(self.viewSkel().kindName, self.getKey())

        if not skel.fromDB(key):
            return None

        return skel

    def canPreview(self) -> bool:
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

        :returns: True, if previewing entries is allowed, False otherwise.
        """
        if not (user := current.user.get()):
            return False

        if user["access"] and "root" in user["access"]:
            return True

        if user["access"] and f"{self.moduleName}-edit" in user["access"]:
            return True

        return False

    def canEdit(self) -> bool:
        """
        Access control function for modification permission.

        Checks if the current user has the permission to edit the singletons entry.

        The default behavior is:
        - If no user is logged in, editing is generally refused.
        - If the user has "root" access, editing is generally allowed.
        - If the user has the modules "edit" permission (module-edit) enabled, editing is allowed.

        It should be overridden for a module-specific behavior.

        .. seealso:: :func:`edit`

        :returns: True, if editing is allowed, False otherwise.
        """
        if not (user := current.user.get()):
            return False

        if user["access"] and "root" in user["access"]:
            return True

        if user["access"] and f"{self.moduleName}-edit" in user["access"]:
            return True

        return False

    def canView(self) -> bool:
        """
        Access control function for viewing permission.

        Checks if the current user has the permission to view the singletons entry.

        The default behavior is:
        - If no user is logged in, viewing is generally refused.
        - If the user has "root" access, viewing is generally allowed.
        - If the user has the modules "view" permission (module-view) enabled, viewing is allowed.

        It should be overridden for a module-specific behavior.

        .. seealso:: :func:`view`

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

        .. seealso:: :func:`edit`, :func:`onEdited`
        """
        pass

    def onEdited(self, skel: SkeletonInstance):
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


Singleton.admin = True
Singleton.vi = True
