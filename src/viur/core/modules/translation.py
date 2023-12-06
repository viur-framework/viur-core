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

    tr_key = StringBone(
        descr="translation key",
        searchable=True,
        unique=UniqueValue(UniqueLockMethod.SameValue, False,
                           "This translation key exist already"),
    )

    translations = StringBone(
        descr="translations",
        searchable=True,
        languages=conf.i18n.available_languages,
    )

    translations_missing = SelectBone(
        descr="missing",
        multiple=True,
        readOnly=True,
        values=conf.i18n.available_languages,
        compute=Compute(
            fn=lambda skel: [lang
                             for lang in conf.i18n.available_languages
                             if not skel["translations"].get(lang)],
            interval=ComputeInterval(ComputeMethod.OnWrite),
        ),
    )

    default_text = StringBone(
        descr="default value",
        readOnly=True,  # TODO: ???
    )

    hint = StringBone(
        descr="hint",
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

    @classmethod
    def toDB(cls, skelValues: SkeletonInstance, **kwargs) -> db.Key:
        # Ensure we have only lowercase keys
        skelValues["tr_key"] = skelValues["tr_key"].lower()
        return super().toDB(skelValues, **kwargs)


class Translation(List):
    kindName = KINDNAME

    def adminInfo(self):
        admin_info = {
            "views": [
                {
                    "name": f"missing translations for {lang}",
                    "filter": {
                        "translations_missing": lang,
                    },
                }
                for lang in conf.i18n.available_languages
            ],
        }
        return admin_info

    roles = {
        "admin": "*",
    }

    def on_item_added_and_edited_and_deleted(self, skel: SkeletonInstance):
        # TODO: debounce this
        # TODO: Can we affect all instances?
        super().on_item_added_and_edited_and_deleted(skel)
        systemTranslations.clear()
        initializeTranslations()
