import typing as t

from .meta import MetaBaseSkel

if t.TYPE_CHECKING:
    from . import RefSkel, Skeleton, SkeletonInstance


def skeletonByKind(kindName: str) -> t.Type["Skeleton"]:
    """
    Returns the Skeleton-Class for the given kindName. That skeleton must exist, otherwise an exception is raised.
    :param kindName: The kindname to retreive the skeleton for
    :return: The skeleton-class for that kind
    """
    assert kindName in MetaBaseSkel._skelCache, f"Unknown skeleton {kindName=}"
    return MetaBaseSkel._skelCache[kindName]


def listKnownSkeletons() -> list[str]:
    """
        :return: A list of all known kindnames (all kindnames for which a skeleton is defined)
    """
    return sorted(MetaBaseSkel._skelCache.keys())


def iterAllSkelClasses() -> t.Iterable["Skeleton"]:
    """
        :return: An iterator that yields each Skeleton-Class once. (Only top-level skeletons are returned, so no
            RefSkel classes will be included)
    """
    for cls in list(MetaBaseSkel._allSkelClasses):  # We'll add new classes here during setSystemInitialized()
        yield cls


class SkelList(list):
    """
        This class is used to hold multiple skeletons together with other, commonly used information.

        SkelLists are returned by Skel().all()...fetch()-constructs and provide additional information
        about the data base query, for fetching additional entries.

        :ivar cursor: Holds the cursor within a query.
        :vartype cursor: str
    """

    __slots__ = (
        "baseSkel",
        "customQueryInfo",
        "getCursor",
        "get_orders",
        "renderPreparation",
    )

    def __init__(self, skel, *items):
        """
            :param baseSkel: The baseclass for all entries in this list
        """
        super().__init__()
        self.baseSkel = skel or {}
        self.getCursor = lambda: None
        self.get_orders = lambda: None
        self.renderPreparation = None
        self.customQueryInfo = {}

        self.extend(items)


# FIXME: REMOVE WITH VIUR4
def remove_render_preparation_deep(skel: t.Any) -> t.Any:
    """Remove renderPreparation of nested skeletons

    _refSkelCache can have renderPreparation too.
    """
    from .instance import SkeletonInstance

    if isinstance(skel, SkeletonInstance):
        skel.renderPreparation = None
        for _, value in skel.items(yieldBoneValues=True):
            remove_render_preparation_deep(value)
    elif isinstance(skel, dict):
        for value in skel.values():
            remove_render_preparation_deep(value)
    elif isinstance(skel, (list, tuple, set)):
        for value in skel:
            remove_render_preparation_deep(value)

    return skel


def without_render_preparation(skel: "SkeletonInstance", full_clone: bool = False) -> "SkeletonInstance":
    """Return the SkeletonInstance without renderPreparation.

    This method is useful (and unfortunately necessary due to the ViUR design)
    if you call python methods from the jinja template that should work on the
    `SkeletonInstance.accessedValues` and not on the `SkeletonInstance.renderAccessedValues`.

    If the SkeletonInstance does not have renderPreparation, it will be returned as is.
    If renderPreparation is enabled, a new SkeletonInstance is created.
    However, unless `full_clone` is True, the SkeletonInstance will use the
    identical objects as the source skeleton. It just "removes" the
    "renderPreparation mode" and keep it for the source skel enabled.
    """
    from . import SkeletonInstance
    if skel.renderPreparation is not None:
        if full_clone:
            skel = skel.clone()
        else:
            src_skel = skel
            # Create a new SkeletonInstance with the same object,
            # but without enabled renderPreparation
            skel = SkeletonInstance(src_skel.skeletonCls, bone_map=src_skel.boneMap)
            skel.accessedValues = src_skel.accessedValues
            skel.dbEntity = src_skel.dbEntity
            skel.errors = src_skel.errors
            skel.is_cloned = src_skel.is_cloned
        assert skel.renderPreparation is None
        skel = remove_render_preparation_deep(skel)
    return skel


def is_skeletoninstance_of(
    obj: t.Any,
    skel_cls: type["Skeleton"],
    *,
    accept_ref_skel: bool = True,
) -> bool:
    """
    Checks whether an object is an SkeletonInstance that belongs to a specific Skeleton class.

    :param obj: The object to check.
    :param skel_cls: The skeleton class that will be checked against ``obj``.
    :param accept_ref_skel: If True, ``obj`` can also be just a RefSkelFor``skel_cls``.
        If False, no ``RefSkel`` is accepted.
    """
    from . import RefSkel, Skeleton, SkeletonInstance

    if not issubclass(skel_cls, Skeleton):
        raise TypeError(f"{skel_cls=} is not a Skeleton.")

    if not isinstance(obj, SkeletonInstance):
        return False
    if issubclass(obj.skeletonCls, skel_cls):
        return True
    if accept_ref_skel and issubclass(obj.skeletonCls, RefSkel) and issubclass(obj.skeletonCls.skeletonCls, skel_cls):
        return True
    return False
