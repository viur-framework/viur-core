import enum
import logging
from datetime import timedelta as td

from viur.core import conf, db, utils
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
        descr="core.translationskel.tr_key.descr",
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
        descr="core.translationskel.translations_missing.descr",
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
        descr="core.translationskel.default_text.descr",
    )

    hint = StringBone(
        descr="core.translationskel.hint.descr",
    )

    usage_filename = StringBone(
        descr="core.translationskel.usage_filename.descr",
        readOnly=True,
    )

    usage_lineno = NumericBone(
        descr="core.translationskel.usage_lineno.descr",
        readOnly=True,
    )

    usage_variables = StringBone(
        descr="core.translationskel.usage_variables.descr",
        readOnly=True,
        multiple=True,
    )

    creator = SelectBone(
        descr="core.translationskel.creator.descr",
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

    def onAdded(self, *args, **kwargs):
        super().onAdded(*args, **kwargs)
        self._reload_translations()

    def onEdited(self, *args, **kwargs):
        super().onEdited(*args, **kwargs)
        self._reload_translations()

    def onDeleted(self, *args, **kwargs):
        super().onDeleted(*args, **kwargs)
        self._reload_translations()

    def _reload_translations(self):
        if (
            self._last_reload is not None
            and self._last_reload - utils.utcNow() < td(minutes=10)
        ):
            # debounce: translations has been reload recently, skip this
            return None
        logging.info("Reload translations")
        # TODO: this affects only the current instance
        self._last_reload = utils.utcNow()
        systemTranslations.clear()
        initializeTranslations()

    _last_reload = None
