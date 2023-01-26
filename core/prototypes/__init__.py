from .list import List
from .singleton import Singleton
from .tree import Tree, TreeSkel


# DEPRECATED ATTRIBUTES HANDLING
def __getattr__(attr):
    if attr in ("BasicApplication", ):
        ret = None

        match attr:
            case "BasicApplication":
                msg = f"Use of `prototypes.BasicApplication` is deprecated; Use `viur.core.Module` instead!"
                from viur.core.module import Module
                ret = Module

        if ret:
            import warnings
            import logging
            warnings.warn(msg, DeprecationWarning, stacklevel=3)
            logging.warning(msg, stacklevel=3)
            return ret

    return super(__import__(__name__).__class__).__getattr__(attr)
