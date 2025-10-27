import typing as t
from .meta import MetaBaseSkel


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
