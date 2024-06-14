import abc
import typing as t

from viur.core.module import Module
from viur.core.skeleton import SkelList, SkeletonInstance


class AbstractRenderer(abc.ABC):
    parent: Module | None = None

    def __init__(self, parent: Module = None):
        super().__init__()
        self.parent = parent

    @property
    @abc.abstractmethod
    def kind(self) -> str:
        """Renderer type specifier"""
        ...

    @abc.abstractmethod
    def list(
        self,
        skellist: SkelList,
        action: str = "list",
        params: t.Any = None,
        **kwargs,
    ) -> str:
        """
        Renders a response with a list of entries.

        :param skellist: List of Skeletons with entries to display.
        :param action: The name of the action, which is passed into the result.
        :param params: Optional data that will be passed unmodified to the template
        """
        ...

    @abc.abstractmethod
    def view(
        self,
        skel: SkeletonInstance,
        action: str = "view",
        params: t.Any = None,
        **kwargs,
    ) -> str:
        """
        Renders a response for viewing an entry.
        """
        ...

    def add(
        self,
        skel: SkeletonInstance,
        action: str = "add",
        params: t.Any = None,
        **kwargs,
    ) -> str:
        """
        Renders a response for adding an entry.
        """
        ...

    def edit(
        self,
        skel: SkeletonInstance,
        action: str = "edit",
        params: t.Any = None,
        **kwargs,
    ) -> str:
        """
        Renders a response for modifying an entry.
        """
        ...
