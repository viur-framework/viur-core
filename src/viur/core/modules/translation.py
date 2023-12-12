import enum

from viur.core import conf, db
from viur.core.bones import *
from viur.core.i18n import KINDNAME, initializeTranslations, systemTranslations, translate
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
        descr="core.translationskel.translations.descr",
        searchable=True,
        languages=conf.i18n.available_dialects,
        params={
            "tooltip": translate(
                "core.translationskel.translations.tooltip",
                "The languages {{main}} are required,\n {{accent}} can be filled out"
            )(main=", ".join(conf.i18n.available_languages),
              accent=", ".join(conf.i18n.language_alias_map.keys())),
        }
    )

    translations_missing = SelectBone(
        descr="translation missing for language",
        multiple=True,
        readOnly=True,
        values=conf.i18n.available_dialects,
        compute=Compute(
            fn=lambda skel: [lang
                             for lang in conf.i18n.available_dialects
                             if not skel["translations"].get(lang)],
            interval=ComputeInterval(ComputeMethod.OnWrite),
        ),
    )

    default_text = StringBone(
        descr="default value",
    )

    hint = StringBone(
        descr="hint (internal only)",
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

    @classmethod
    def preProcessSerializedData(cls, skelValues: SkeletonInstance, entity: db.Entity) -> db.Entity:
        # Backward-compatibility: re-add the key for viur-core < v3.6
        entity["key"] = skelValues["tr_key"]
        return super().preProcessSerializedData(skelValues, entity)


class Translation(List):
    kindName = KINDNAME

    def adminInfo(self):
        admin_info = {
            "name": "translations",
            "views": [
                {
                    "name": f"missing translations for {lang}",
                    "filter": {
                        "translations_missing": lang,
                    },
                }
                for lang in conf.i18n.available_dialects
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
