from .base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity, UniqueValue, UniqueLockMethod, MultipleConstraints
from .boolean import BooleanBone
from .captcha import CaptchaBone
from .color import ColorBone
from .credential import CredentialBone
from .date import DateBone
from .email import EmailBone
from .file import FileBone
from .key import KeyBone
from .numeric import NumericBone
from .password import PasswordBone
from .randomslice import RandomSliceBone
from .raw import RawBone
from .record import RecordBone
from .relational import RelationalBone, RelationalConsistency, RelationalUpdateLevel
from .selectcountry import SelectCountryBone
from .select import SelectBone
from .sortindex import SortIndexBone
from .spatial import SpatialBone
from .string import StringBone
from .text import TextBone
from .treeleaf import TreeLeafBone
from .treenode import TreeNodeBone
from .user import UserBone

# Expose only specific names
__all = [
    "BaseBone",
    "BooleanBone",
    "CaptchaBone",
    "ColorBone",
    "CredentialBone",
    "DateBone",
    "EmailBone",
    "FileBone",
    "KeyBone",
    "MultipleConstraints",
    "NumericBone",
    "PasswordBone",
    "RandomSliceBone",
    "RawBone",
    "ReadFromClientError",
    "ReadFromClientErrorSeverity",
    "RecordBone",
    "RelationalBone",
    "RelationalConsistency",
    "SelectBone",
    "SelectCountryBone",
    "SortIndexBone",
    "SpatialBone",
    "StringBone",
    "TextBone",
    "TreeLeafBone",
    "TreeNodeBone",
    "UniqueLockMethod",
    "UniqueValue",
    "UserBone",
]

for __cls_name, __cls in locals().copy().items():
    if __cls_name.startswith("__"):
        continue

    if __cls_name.endswith("Bone"):
        __old_cls_name = __cls_name[0].lower() + __cls_name[1:]

        __all += [__old_cls_name]

        # Dynamically create a class providing a deprecation logging message for every lower-case bone name
        def __generate_deprecation_constructor(cls, cls_name, old_cls_name):
            def __init__(self, *args, **kwargs):
                import logging, warnings
                logging.warning(f"Use of class '{old_cls_name}' is deprecated, use '{cls_name}' instead.")
                warnings.warn(f"Use of class '{old_cls_name}' is deprecated, use '{cls_name}' instead.")
                cls.__init__(self, *args, **kwargs)

            return __init__

        locals()[__old_cls_name] = type(__old_cls_name, (__cls, ), {
            "__init__": __generate_deprecation_constructor(__cls, __cls_name, __old_cls_name)
        })

        #print(__old_cls_name, "installed as ", locals()[__old_cls_name], issubclass(locals()[__old_cls_name], __cls))

__all__ = __all
