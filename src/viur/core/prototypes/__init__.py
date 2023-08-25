from .list import List
from .singleton import Singleton
from .tree import Tree, TreeSkel


# DEPRECATED ATTRIBUTES HANDLING
def __getattr__(attr):
    if attr in ("BasicApplication", ):
        ret = None

        match attr:
            case "BasicApplication":
                msg = f"The use of `prototypes.BasicApplication` is deprecated; " \
                      f"Please use `viur.core.prototypes.skelmodule.SkelModule` instead!"
                from viur.core.prototypes.skelmodule import SkelModule
                ret = SkelModule

        if ret:
            import warnings
            import logging
            warnings.warn(msg, DeprecationWarning, stacklevel=3)
            logging.warning(msg, stacklevel=3)
            return ret

    return super(__import__(__name__).__class__).__getattr__(attr)
