import inspect
import logging  # noqa
import os
import string
import sys
import typing as t

from .adapter import ViurTagsSearchAdapter
from .. import utils
from ..bones.base import BaseBone, getSystemInitialized
from ..config import conf

_UNDEFINED_KINDNAME = object()
ABSTRACT_SKEL_CLS_SUFFIX = "AbstractSkel"

Skeleton_Cls = t.TypeVar("Skeleton_Cls", bound="BaseSkeleton")
"""TypeVar for generic skeleton typing.

Use this to annotate functions and classes that work with a specific, but not yet known,
Skeleton subclass. The type checker then knows which concrete Skeleton is in use and can
validate bone access.

Example — typed helper function::

    from viur.core.skeleton import Skeleton_Cls, SkeletonInstance

    def clone_and_set_owner(skel: SkeletonInstance[Skeleton_Cls], owner: str) -> SkeletonInstance[Skeleton_Cls]:
        cloned = skel.clone()
        cloned["owner"] = owner
        return cloned

Example — typed module override::

    class ProductModule(List):
        def editSkel(self) -> SkeletonInstance[ProductSkel]:
            skel = super().editSkel()
            skel.price.readOnly = True
            return skel

When calling a classmethod on a concrete Skeleton, use ``t.Self`` instead so the type checker
automatically narrows to the calling class::

    class BaseSkeleton:
        @classmethod
        def fromClient(cls, skel: SkeletonInstance[t.Self], data: dict) -> bool: ...

    # Calling on a concrete class: type checker knows skel is SkeletonInstance[ProductSkel]
    ProductSkel.fromClient(skel, request.POST)
"""


class MetaBaseSkel(type):
    """
        This is the metaclass for Skeletons.
        It is used to enforce several restrictions on bone names, etc.
    """
    _skelCache = {}  # Mapping kindName -> SkelCls
    _allSkelClasses = set()  # list of all known skeleton classes (including Ref and Mail-Skels)

    # List of reserved keywords and function names
    __reserved_keywords = {
        "all",
        "bounce",
        "clone",
        "cursor",
        "delete",
        "errors",
        "fromClient",
        "fromDB",
        "get",
        "getCurrentSEOKeys",
        "items",
        "keys",
        "limit",
        "orderby",
        "orderdir",
        "patch",
        "postDeletedHandler",
        "postSavedHandler",
        "preProcessBlobLocks",
        "preProcessSerializedData",
        "read",
        "readonly",
        "refresh",
        "self",
        "serialize",
        "setBoneValue",
        "structure",
        "style",
        "toDB",
        "unserialize",
        "values",
        "write",
    }

    __allowed_chars = string.ascii_letters + string.digits + "_"

    def __init__(cls, name, bases, dct, **kwargs):
        cls.__boneMap__ = MetaBaseSkel.generate_bonemap(cls)

        if not getSystemInitialized() and not cls.__name__.endswith(ABSTRACT_SKEL_CLS_SUFFIX):
            MetaBaseSkel._allSkelClasses.add(cls)

        super().__init__(name, bases, dct)

    @staticmethod
    def generate_bonemap(cls):
        """
        Recursively constructs a dict of bones from
        """
        map = {}

        for base in cls.__bases__:
            if "__viurBaseSkeletonMarker__" in dir(base):
                map |= MetaBaseSkel.generate_bonemap(base)

        for key in cls.__dict__:
            prop = getattr(cls, key)

            if isinstance(prop, BaseBone):
                if not all([c in MetaBaseSkel.__allowed_chars for c in key]):
                    raise AttributeError(f"Invalid bone name: {key!r} contains invalid characters")
                elif key in MetaBaseSkel.__reserved_keywords:
                    raise AttributeError(f"Invalid bone name: {key!r} is reserved and cannot be used")

                map[key] = prop

            elif prop is None and key in map:  # Allow removing a bone in a subclass by setting it to None
                del map[key]

        return map

    def __setattr__(self, key, value):
        super().__setattr__(key, value)
        if isinstance(value, BaseBone):
            # Call BaseBone.__set_name__ manually for bones that are assigned at runtime
            value.__set_name__(self, key)


class MetaSkel(MetaBaseSkel):

    def __init__(cls, name, bases, dct, **kwargs):
        super().__init__(name, bases, dct, **kwargs)

        relNewFileName = inspect.getfile(cls) \
            .replace(str(conf.instance.project_base_path), "") \
            .replace(str(conf.instance.core_base_path), "")

        # Check if we have an abstract skeleton
        if cls.__name__.endswith(ABSTRACT_SKEL_CLS_SUFFIX):
            # Ensure that it doesn't have a kindName
            assert cls.kindName is _UNDEFINED_KINDNAME or cls.kindName is None, \
                "Abstract Skeletons can't have a kindName"
            # Prevent any further processing by this class; it has to be sub-classed before it can be used
            return

        # Automatic determination of the kindName, if the class is not part of viur.core.
        if (
            cls.kindName is _UNDEFINED_KINDNAME
            and not relNewFileName.strip(os.path.sep).startswith("viur")
            and "viur_doc_build" not in dir(sys)  # do not check during documentation build
        ):
            if cls.__name__.endswith("Skel"):
                cls.kindName = cls.__name__.lower()[:-4]
            else:
                cls.kindName = cls.__name__.lower()

        # Try to determine which skeleton definition takes precedence
        if cls.kindName and cls.kindName is not _UNDEFINED_KINDNAME and cls.kindName in MetaBaseSkel._skelCache:
            relOldFileName = inspect.getfile(MetaBaseSkel._skelCache[cls.kindName]) \
                .replace(str(conf.instance.project_base_path), "") \
                .replace(str(conf.instance.core_base_path), "")
            idxOld = min(
                [x for (x, y) in enumerate(conf.skeleton_search_path) if relOldFileName.startswith(y)] + [999])
            idxNew = min(
                [x for (x, y) in enumerate(conf.skeleton_search_path) if relNewFileName.startswith(y)] + [999])
            if idxNew == 999:
                # We could not determine a priority for this class as its from a path not listed in the config
                raise NotImplementedError(
                    "Skeletons must be defined in a folder listed in conf.skeleton_search_path")
            elif idxOld < idxNew:  # Lower index takes precedence
                # The currently processed skeleton has a lower priority than the one we already saw - just ignore it
                return
            elif idxOld > idxNew:
                # The currently processed skeleton has a higher priority, use that from now
                MetaBaseSkel._skelCache[cls.kindName] = cls
            else:  # They seem to be from the same Package - raise as something is messed up
                raise ValueError(f"Duplicate definition for {cls.kindName} in {relNewFileName} and {relOldFileName}")

        # Ensure that all skeletons are defined in folders listed in conf.skeleton_search_path
        if (
            not any([relNewFileName.startswith(path) for path in conf.skeleton_search_path])
            and "viur_doc_build" not in dir(sys)  # do not check during documentation build
        ):
            raise NotImplementedError(
                f"""{relNewFileName} must be defined in a folder listed in {conf.skeleton_search_path}""")

        if cls.kindName and cls.kindName is not _UNDEFINED_KINDNAME:
            MetaBaseSkel._skelCache[cls.kindName] = cls

        # Auto-Add ViUR Search Tags Adapter if the skeleton has no adapter attached
        if cls.database_adapters is _UNDEFINED_KINDNAME:
            cls.database_adapters = ViurTagsSearchAdapter()

        # Always ensure that skel.database_adapters is an iterable
        cls.database_adapters = utils.ensure_iterable(cls.database_adapters)
