from .list import List
from .singleton import Singleton
from .tree import Tree, TreeSkel


# DEPRECATED ATTRIBUTES HANDLING
def __getattr__(attr):
    if attr in ("BasicApplication", ):
        ret = None

        match attr:
            case "BasicApplication":
                msg = f"Use of `prototypes.BasicApplication` is deprecated; Use `base.SkelModule` instead!"
                from viur.core.base.skelmodule import SkelModule
                ret = SkelModule

        if ret:
            import warnings
            import logging
            warnings.warn(msg, DeprecationWarning, stacklevel=3)
            logging.warning(msg, stacklevel=3)
            return ret

    return super(__import__(__name__).__class__).__getattr__(attr)
