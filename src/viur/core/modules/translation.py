import enum

from viur.core import conf, db
from viur.core.bones import *
from viur.core.i18n import KINDNAME, initializeTranslations, systemTranslations
from viur.core.prototypes.list import List
from viur.core.skeleton import Skeleton, SkeletonInstance


class Creator(enum.Enum):
    VIUR = "viur"
    USER = "user"


class TranslationSkel(Skeleton):
    kindName = KINDNAME

    """
    key = StringBone(
        descr="Key",
    )
    """

    tr_key = StringBone(
        descr="Tr Key",
        readOnly=True,
        unique=UniqueValue(UniqueLockMethod.SameValue, False,
                           "This translation key exist already"),
    )

    translations = StringBone(
        descr="Übersetzungen",
        # required=True,
        languages=conf.i18n.available_languages,
    )

    default_value = StringBone(
        descr="Default Value",
        readOnly=True,  # TODO: ???
    )

    hint = StringBone(
        descr="Hint",
        readOnly=True,  # TODO: ???
    )

    usage_filename = StringBone(
        descr="Used and added from this file",
        readOnly=True,
    )

    usage_lineno = NumericBone(
        descr="Used and added from this lineno",
        readOnly=True,
    )

    usage_variables = StringBone(
        descr="Variables",
        readOnly=True,
        multiple=True,
    )

    creator = SelectBone(
        descr="Creator",
        values=Creator,
    )

    # @classmethod
    # def fromDB(cls, skelValues: SkeletonInstance, key: Union[str, db.Key]) -> bool:
    #     res = super().fromDB(skelValues, key)
    #     skelValues["tr_key"] = skelValues.dbEntity["key"]
    #     return res
    #
    # @classmethod
    # def preProcessSerializedData(cls, skelValues, entity):
    #     entity["key"] = skelValues["tr_key"].lower()
    #     return entity

    @classmethod
    def toDB(cls, skelValues: SkeletonInstance, **kwargs) -> db.Key:
        # Ensure we have only lowercase keys
        skelValues["tr_key"] = skelValues["tr_key"].lower()
        return super().toDB(skelValues, **kwargs)


class Translation(List):
    kindName = KINDNAME

    # adminInfo = {
    #     "name": translate("translations"),
    # }

    roles = {
        "admin": "*",
    }

    """
    def canAdd(self) -> bool:
        return False

    def addSkel(self, *args, **kwargs) -> SkeletonInstance:
        skel: TranslationSkel = self.baseSkel(*args, **kwargs).clone()
        skel.tr_key.readOnly = False
        return skel

    def canDelete(self, skel: SkeletonInstance) -> bool:
        return False

    def canEdit(self, skel: SkeletonInstance) -> bool:
        # Sorry, but this should avoid accidents because WIP :)
        return (user := current.user.get()) and user["name"] == "se@mausbrand.de"
    """

    def on_item_added_and_edited_and_deleted(self, skel: SkeletonInstance):
        # TODO: debounce this
        # TODO: Can we affect all instances?
        super().on_item_added_and_edited_and_deleted(skel)
        systemTranslations.clear()
        initializeTranslations()
