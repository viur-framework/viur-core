import logging
import warnings

from .adapter import DatabaseAdapter, ViurTagsSearchAdapter
from .instance import SkeletonInstance
from .meta import ABSTRACT_SKEL_CLS_SUFFIX, BaseSkeleton, MetaBaseSkel, MetaSkel
from .relskel import RefSkel, RelSkel
from .skeleton import SeoKeyBone, Skeleton, _UNDEFINED_KINDNAME
from .tasks import SkelIterTask, SkeletonMaintenanceTask, update_relations
from .utils import (  # noqa
    SkelList,
    is_skeletoninstance_of,
    iterAllSkelClasses,
    listKnownSkeletons,
    remove_render_preparation_deep,
    skeletonByKind,
    without_render_preparation,
)

# DEPRECATED ATTRIBUTES HANDLING
# FIXME: REMOVE WITH VIUR4

from ..bones.base import getSystemInitialized as _getSystemInitialized
from ..db import KeyType as _KeyType

__DEPRECATED_NAMES = {
    # stuff prior viur-core < 3.6
    "seoKeyBone": ("SeoKeyBone", SeoKeyBone),
    # stuff prior viur-core < 3.8
    "getSystemInitialized": ("bones.base.getSystemInitialized", _getSystemInitialized),
    "KeyType": ("db.KeyType", _KeyType),
}

def __getattr__(attr: str) -> object:
    if entry := __DEPRECATED_NAMES.get(attr):
        func = entry[1]
        msg = f"{attr} was replaced by {entry[0]}"
        warnings.warn(msg, DeprecationWarning, stacklevel=2)
        logging.warning(msg, stacklevel=2)
        return func

    return super(__import__(__name__).__class__).__getattribute__(attr)


__all__ = [
    ABSTRACT_SKEL_CLS_SUFFIX,
    BaseSkeleton,
    DatabaseAdapter,
    MetaBaseSkel,
    MetaSkel,
    RefSkel,
    RelSkel,
    SeoKeyBone,
    SkelIterTask,
    SkelList,
    Skeleton,
    SkeletonInstance,
    SkeletonMaintenanceTask,
    ViurTagsSearchAdapter,
    _UNDEFINED_KINDNAME,
    is_skeletoninstance_of,
    iterAllSkelClasses,
    listKnownSkeletons,
    remove_render_preparation_deep,
    skeletonByKind,
    update_relations,
    without_render_preparation,
]
