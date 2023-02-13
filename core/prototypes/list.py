import logging
from typing import Any, Optional

from viur.core import db, errors, exposed, forcePost, forceSSL, securitykey, utils
from viur.core.cache import flushCache
from viur.core.prototypes import BasicApplication
from viur.core.skeleton import SkeletonInstance
from viur.core.utils import currentRequest


class List(BasicApplication):
    """
        The list prototype will only handle a single kind and arrange it's entities in a flat list.
        This list can be filtered and/or sorted but there is no hierarchy/relationship between the items
        in that list.
    """

    accessRights = ["add", "edit", "view", "delete"]  #: Possible access rights for this app

    def adminInfo(self):
        return {
            "name": self.__class__.__name__,  # Module name as shown in the admin tools
            "handler": "list",  # Which handler to invoke
            "icon": "icon-list"  # Icon for this module
        }

    def __init__(self, moduleName, modulePath, *args, **kwargs):
        super(List, self).__init__(moduleName, modulePath, *args, **kwargs)

    def viewSkel(self, *args, **kwargs) -> SkeletonInstance:
        """
            Retrieve a new instance of a :class:`viur.core.skeleton.SkeletonInstance` that is used by the application
            for viewing an existing entry from the list.

            The default is a Skeleton instance returned by :func:`~baseSkel`.

            This SkeletonInstance can be post-processed (just returning a subskel or manually removing single bones) - which
            is the recommended way to ensure a given user cannot see certain fields. A Jinja-Template may choose not to
            display certain bones, but if the json or xml render is attached (or the user can use the vi or admin render)
            he could still see all values. This also prevents the user from filtering by these bones, so no binary search
            is possible.

            .. seealso:: :func:`addSkel`, :func:`editSkel`, :func:`~baseSkel`

            :return: Returns a Skeleton instance for viewing an entry.
        """
        return self.baseSkel(*args, **kwargs)

    def addSkel(self, *args, **kwargs) -> SkeletonInstance:
        """
            Retrieve a new instance of a :class:`viur.core.skeleton.Skeleton` that is used by the application
            for adding an entry to the list.

            The default is a Skeleton instance returned by :func:`~baseSkel`.

            Like in :func:`viewSkel`, the skeleton can be post-processed. Bones that are being removed aren't visible
            and cannot be set, but it's also possible to just set a bone to readOnly (revealing it's value to the user,
            but preventing any modification. It's possible to pre-set values on that skeleton (and if that bone is
            readOnly, enforcing these values).

            .. seealso:: :func:`viewSkel`, :func:`editSkel`, :func:`~baseSkel`

            :return: Returns a Skeleton instance for adding an entry.
        """
        return self.baseSkel(*args, **kwargs)

    def editSkel(self, *args, **kwargs) -> SkeletonInstance:
        """
            Retrieve a new instance of a :class:`viur.core.skeleton.Skeleton` that is used by the application
            for editing an existing entry from the list.

            The default is a Skeleton instance returned by :func:`~baseSkel`.

            Like in :func:`viewSkel`, the skeleton can be post-processed. Bones that are being removed aren't visible
            and cannot be set, but it's also possible to just set a bone to readOnly (revealing it's value to the user,
            but preventing any modification.

            .. seealso:: :func:`viewSkel`, :func:`editSkel`, :func:`~baseSkel`

            :return: Returns a Skeleton instance for editing an entry.
        """
        return self.baseSkel(*args, **kwargs)

    ## External exposed functions

    @exposed
    @forcePost
    def preview(self, skey: str, *args, **kwargs) -> Any:
        """
            Renders data for an entry, without reading from the database.
            This function allows to preview an entry without writing it to the database.

            Any entity values are provided via *kwargs*.

            The function uses the viewTemplate of the application.

            :returns: The rendered representation of the the supplied data.
        """
        if not self.canPreview():
            raise errors.Unauthorized()

        if not securitykey.validate(skey, useSessionKey=True):
            raise errors.PreconditionFailed()

        skel = self.viewSkel()
        skel.fromClient(kwargs)

        return self.render.view(skel)

    @exposed
    def structure(self, *args, **kwargs) -> Any:
        """
            :returns: Returns the structure of our skeleton as used in list/view. Values are the defaultValues set
                in each bone.

            :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
        """
        skel = self.viewSkel()
        if not self.canAdd():  # We can't use canView here as it would require passing a skeletonInstance.
            # As a fallback, we'll check if the user has the permissions to view at least one entry
            qry = self.listFilter(skel.all())
            if not qry or not qry.getEntry():
                raise errors.Unauthorized()
        return self.render.view(skel)

    @exposed
    def view(self, *args, **kwargs) -> Any:
        """
            Prepares and renders a single entry for viewing.

            The entry is fetched by its entity key, which either is provided via *kwargs["key"]*,
            or as the first parameter in *args*. The function performs several access control checks
            on the requested entity before it is rendered.

            .. seealso:: :func:`viewSkel`, :func:`canView`, :func:`onView`

            :returns: The rendered representation of the requested entity.

            :raises: :exc:`viur.core.errors.NotAcceptable`, when no *key* is provided.
            :raises: :exc:`viur.core.errors.NotFound`, when no entry with the given *key* was found.
            :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
        """
        if "key" in kwargs:
            key = kwargs["key"]
        elif len(args) >= 1:
            key = args[0]
        else:
            raise errors.NotAcceptable()
        if not key:
            raise errors.NotAcceptable()
        # We return a single entry for viewing
        skel = self.viewSkel()
        if not skel.fromDB(key):
            raise errors.NotFound()
        if not self.canView(skel):
            raise errors.Forbidden()
        self.onView(skel)
        return self.render.view(skel)

    @exposed
    def list(self, *args, **kwargs) -> Any:
        """
            Prepares and renders a list of entries.

            All supplied parameters are interpreted as filters for the elements displayed.

            Unlike other ViUR BasicApplications, the access control in this function is performed
            by calling the function :func:`listFilter`, which updates the query-filter to match only
            elements which the user is allowed to see.

            .. seealso:: :func:`listFilter`, :func:`viur.core.db.mergeExternalFilter`

            :returns: The rendered list objects for the matching entries.

            :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
        """
        query = self.listFilter(self.viewSkel().all().mergeExternalFilter(kwargs))  # Access control
        if query is None:
            raise errors.Unauthorized()
        res = query.fetch()
        return self.render.list(res)

    @forceSSL
    @exposed
    def edit(self, *args, **kwargs) -> Any:
        """
            Modify an existing entry, and render the entry, eventually with error notes on incorrect data.
            Data is taken by any other arguments in *kwargs*.

            The entry is fetched by its entity key, which either is provided via *kwargs["key"]*,
            or as the first parameter in *args*. The function performs several access control checks
            on the requested entity before it is modified.

            .. seealso:: :func:`editSkel`, :func:`onEdit`, :func:`onEdited`, :func:`canEdit`

            :returns: The rendered, edited object of the entry, eventually with error hints.

            :raises: :exc:`viur.core.errors.NotAcceptable`, when no *key* is provided.
            :raises: :exc:`viur.core.errors.NotFound`, when no entry with the given *key* was found.
            :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
            :raises: :exc:`viur.core.errors.PreconditionFailed`, if the *skey* could not be verified.
        """
        skey = kwargs.get("skey", "")
        if "key" in kwargs:
            key = kwargs["key"]
        elif len(args) == 1:
            key = args[0]
        else:
            raise errors.NotAcceptable()
        skel = self.editSkel()
        if not skel.fromDB(key):
            raise errors.NotFound()
        if not self.canEdit(skel):
            raise errors.Unauthorized()
        if (len(kwargs) == 0  # no data supplied
            or not currentRequest.get().isPostRequest  # failure if not using POST-method
            or not skel.fromClient(kwargs)  # failure on reading into the bones
            or ("bounce" in kwargs and kwargs["bounce"] == "1")  # review before changing
        ):
            # render the skeleton in the version it could as far as it could be read.
            return self.render.edit(skel)
        if not securitykey.validate(skey, useSessionKey=True):
            raise errors.PreconditionFailed()

        self.onEdit(skel)
        skel.toDB()  # write it!
        self.onEdited(skel)

        return self.render.editSuccess(skel)

    @forceSSL
    @exposed
    def add(self, *args, **kwargs) -> Any:
        """
            Add a new entry, and render the entry, eventually with error notes on incorrect data.
            Data is taken by any other arguments in *kwargs*.

            The function performs several access control checks on the requested entity before it is added.

            .. seealso:: :func:`addSkel`, :func:`onAdd`, :func:`onAdded`, :func:`canAdd`

            :returns: The rendered, added object of the entry, eventually with error hints.

            :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
            :raises: :exc:`viur.core.errors.PreconditionFailed`, if the *skey* could not be verified.
        """
        skey = kwargs.get("skey", "")
        if not self.canAdd():
            raise errors.Unauthorized()
        skel = self.addSkel()
        if (len(kwargs) == 0  # no data supplied
            or not currentRequest.get().isPostRequest  # failure if not using POST-method
            or not skel.fromClient(kwargs)  # failure on reading into the bones
            or ("bounce" in kwargs and kwargs["bounce"] == "1")  # review before adding
        ):
            # render the skeleton in the version it could as far as it could be read.
            return self.render.add(skel)
        if not securitykey.validate(skey, useSessionKey=True):
            raise errors.PreconditionFailed()

        self.onAdd(skel)
        skel.toDB()
        self.onAdded(skel)

        return self.render.addSuccess(skel)

    @forceSSL
    @forcePost
    @exposed
    def delete(self, key: str, skey, *args, **kwargs) -> Any:
        """
            Delete an entry.

            The function runs several access control checks on the data before it is deleted.

            .. seealso:: :func:`canDelete`, :func:`editSkel`, :func:`onDeleted`

            :returns: The rendered, deleted object of the entry.

            :raises: :exc:`viur.core.errors.NotFound`, when no entry with the given *key* was found.
            :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
            :raises: :exc:`viur.core.errors.PreconditionFailed`, if the *skey* could not be verified.
        """

        skel = self.editSkel()
        if not skel.fromDB(key):
            raise errors.NotFound()

        if not self.canDelete(skel):
            raise errors.Unauthorized()

        if not securitykey.validate(skey, useSessionKey=True):
            raise errors.PreconditionFailed()

        self.onDelete(skel)
        skel.delete()
        self.onDeleted(skel)

        return self.render.deleteSuccess(skel)

    @exposed
    def index(self, *args, **kwargs) -> Any:
        """
            Default, SEO-Friendly fallback for view and list.

            :param args: The first argument - if provided - is interpreted as seoKey.
            :param kwargs: Used for the fallback list.
            :return: The rendered entity or list.
        """
        if args and args[0]:
            # We probably have a Database or SEO-Key here
            seoKey = str(args[0]).lower()
            skel = self.viewSkel().all(_excludeFromAccessLog=True).filter("viur.viurActiveSeoKeys =", seoKey).getSkel()
            if skel:
                db.currentDbAccessLog.get(set()).add(skel["key"])
                if not self.canView(skel):
                    raise errors.Forbidden()
                seoUrl = utils.seoUrlToEntry(self.moduleName, skel)
                # Check whether this is the current seo-key, otherwise redirect to it
                if currentRequest.get().request.path != seoUrl:
                    raise errors.Redirect(seoUrl, status=301)
                self.onView(skel)
                return self.render.view(skel)
        # This was unsuccessfully, we'll render a list instead
        if not kwargs:
            kwargs = self.getDefaultListParams()
        return self.list(**kwargs)

    def getDefaultListParams(self):
        return {}

    ## Default access control functions

    def listFilter(self, query: db.Query) -> Optional[db.Query]:
        """
            Access control function on item listing.

            This function is invoked by the :func:`list` renderer and the related Jinja2 fetching function,
            and is used to modify the provided filter parameter to match only items that the current user
            is allowed to see.

            :param query: Query which should be altered.

            :returns: The altered filter, or None if access is not granted.
        """
        user = utils.getCurrentUser()

        if user and ("%s-view" % self.moduleName in user["access"] or "root" in user["access"]):
            return query

        return None

    def canView(self, skel: SkeletonInstance) -> bool:
        """
            Checks if the current user can view the given entry.
            Should be identical to what's allowed by listFilter.
            By default, `meth:listFilter` is used to determine what's allowed and whats not; but this
            method can be overridden for performance improvements (to eliminate that additional database access).
            :param skel: The entry we check for
            :return: True if the current session is authorized to view that entry, False otherwise
        """
        # We log the key we're querying by hand so we don't have to lock on the entire kind in our query
        db.currentDbAccessLog.get(set()).add(skel["key"])
        query = self.viewSkel().all(_excludeFromAccessLog=True).mergeExternalFilter({"key": skel["key"]})
        query = self.listFilter(query)  # Access control

        if query is None:
            return False

        if not query.getEntry():
            return False

        return True

    def canAdd(self) -> bool:
        """
            Access control function for adding permission.

            Checks if the current user has the permission to add a new entry.

            The default behavior is:
            - If no user is logged in, adding is generally refused.
            - If the user has "root" access, adding is generally allowed.
            - If the user has the modules "add" permission (module-add) enabled, adding is allowed.

            It should be overridden for a module-specific behavior.

            .. seealso:: :func:`add`

            :returns: True, if adding entries is allowed, False otherwise.
        """
        user = utils.getCurrentUser()
        if not user:
            return False

        # root user is always allowed.
        if user["access"] and "root" in user["access"]:
            return True

        # user with add-permission is allowed.
        if user and user["access"] and "%s-add" % self.moduleName in user["access"]:
            return True

        return False

    def canPreview(self) -> bool:
        """
            Access control function for preview permission.

            Checks if the current user has the permission to preview an entry.

            The default behavior is:
            - If no user is logged in, previewing is generally refused.
            - If the user has "root" access, previewing is generally allowed.
            - If the user has the modules "add" or "edit" permission (module-add, module-edit) enabled, \
            previewing is allowed.

            It should be overridden for module-specific behavior.

            .. seealso:: :func:`preview`

            :returns: True, if previewing entries is allowed, False otherwise.
        """
        user = utils.getCurrentUser()
        if not user:
            return False

        if user["access"] and "root" in user["access"]:
            return True

        if (user and user["access"]
            and ("%s-add" % self.moduleName in user["access"]
                 or "%s-edit" % self.moduleName in user["access"])):
            return True

        return False

    def canEdit(self, skel: SkeletonInstance) -> bool:
        """
            Access control function for modification permission.

            Checks if the current user has the permission to edit an entry.

            The default behavior is:
            - If no user is logged in, editing is generally refused.
            - If the user has "root" access, editing is generally allowed.
            - If the user has the modules "edit" permission (module-edit) enabled, editing is allowed.

            It should be overridden for a module-specific behavior.

            .. seealso:: :func:`edit`

            :param skel: The Skeleton that should be edited.

            :returns: True, if editing entries is allowed, False otherwise.
        """
        user = utils.getCurrentUser()
        if not user:
            return False

        if user["access"] and "root" in user["access"]:
            return True

        if user and user["access"] and "%s-edit" % self.moduleName in user["access"]:
            return True

        return False

    def canDelete(self, skel: SkeletonInstance) -> bool:
        """
            Access control function for delete permission.

            Checks if the current user has the permission to delete an entry.

            The default behavior is:
            - If no user is logged in, deleting is generally refused.
            - If the user has "root" access, deleting is generally allowed.
            - If the user has the modules "deleting" permission (module-delete) enabled, \
             deleting is allowed.

            It should be overridden for a module-specific behavior.

            :param skel: The Skeleton that should be deleted.

            .. seealso:: :func:`delete`

            :returns: True, if deleting entries is allowed, False otherwise.
        """
        user = utils.getCurrentUser()

        if not user:
            return False

        if user["access"] and "root" in user["access"]:
            return True

        if user and user["access"] and "%s-delete" % self.moduleName in user["access"]:
            return True

        return False

    ## Override-able event-hooks

    def onAdd(self, skel: SkeletonInstance):
        """
            Hook function that is called before adding an entry.

            It can be overridden for a module-specific behavior.

            :param skel: The Skeleton that is going to be added.

            .. seealso:: :func:`add`, :func:`onAdded`
        """
        pass

    def onAdded(self, skel: SkeletonInstance):
        """
            Hook function that is called after adding an entry.

            It should be overridden for a module-specific behavior.
            The default is writing a log entry.

            :param skel: The Skeleton that has been added.

            .. seealso:: :func:`add`, , :func:`onAdd`
        """
        logging.info("Entry added: %s" % skel["key"])
        flushCache(kind=skel.kindName)
        user = utils.getCurrentUser()
        if user:
            logging.info("User: %s (%s)" % (user["name"], user["key"]))

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
            Hook function that is called after modifying an entry.

            It should be overridden for a module-specific behavior.
            The default is writing a log entry.

            :param skel: The Skeleton that has been modified.

            .. seealso:: :func:`edit`, :func:`onEdit`
        """
        logging.info("Entry changed: %s" % skel["key"])
        flushCache(key=skel["key"])
        user = utils.getCurrentUser()
        if user:
            logging.info("User: %s (%s)" % (user["name"], user["key"]))

    def onView(self, skel: SkeletonInstance):
        """
            Hook function that is called when viewing an entry.

            It should be overridden for a module-specific behavior.
            The default is doing nothing.

            :param skel: The Skeleton that is viewed.

            .. seealso:: :func:`view`
        """
        pass

    def onDelete(self, skel: SkeletonInstance):
        """
            Hook function that is called before deleting an entry.

            It can be overridden for a module-specific behavior.

            :param skel: The Skeleton that is going to be deleted.

            .. seealso:: :func:`delete`, :func:`onDeleted`
        """
        pass

    def onDeleted(self, skel: SkeletonInstance):
        """
            Hook function that is called after deleting an entry.

            It should be overridden for a module-specific behavior.
            The default is writing a log entry.

            :param skel: The Skeleton that has been deleted.

            .. seealso:: :func:`delete`, :func:`onDelete`
        """
        logging.info("Entry deleted: %s" % skel["key"])
        flushCache(key=skel["key"])
        user = utils.getCurrentUser()
        if user:
            logging.info("User: %s (%s)" % (user["name"], user["key"]))


List.admin = True
List.html = True
List.vi = True
