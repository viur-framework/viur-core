from viur.core.bones.base import BaseBone, UniqueValue, UniqueLockMethod, MultipleConstraints
from viur.core.bones.boolean import BooleanBone
from viur.core.bones.captcha import CaptchaBone
from viur.core.bones.color import ColorBone
from viur.core.bones.credential import CredentialBone
from viur.core.bones.date import DateBone
from viur.core.bones.email import EmailBone
from viur.core.bones.file import FileBone
from viur.core.bones.key import KeyBone
from viur.core.bones.numeric import NumericBone
from viur.core.bones.password import PasswordBone
from viur.core.bones.randomslice import RandomSliceBone
from viur.core.bones.raw import RawBone
from viur.core.bones.record import RecordBone
from viur.core.bones.relational import RelationalBone, RelationalConsistency
from viur.core.bones.selectcountry import SelectCountryBone
from viur.core.bones.select import SelectBone
from viur.core.bones.spatial import SpatialBone
from viur.core.bones.string import StringBone
from viur.core.bones.text import TextBone
from viur.core.bones.treeleaf import TreeLeafBone
from viur.core.bones.treenode import TreeNodeBone
from viur.core.bones.user import UserBone


# Dynamically create a class providing a deprecation logging message for every lower-case bone name
for __cls_name, __cls in locals().copy().items():
	if __cls_name.startswith("__"):
		continue

	if __cls_name.endswith("Bone"):
		__old_cls_name = __cls_name[0].lower() + __cls_name[1:]

		def __generate_deprecation_constructor(cls, cls_name, old_cls_name):
			def __init__(self, *args, **kwargs):
				import logging
				logging.warning(f"Use of class '{old_cls_name}' is deprecated, use '{cls_name}' instead.")
				cls.__init__(self, *args, **kwargs)

			return __init__

		locals()[__old_cls_name] = type(__old_cls_name, (__cls, ), {
			"__init__": __generate_deprecation_constructor(__cls, __cls_name, __old_cls_name)
		})

		#print(__old_cls_name, "installed as ", locals()[__old_cls_name], issubclass(locals()[__old_cls_name], __cls))
