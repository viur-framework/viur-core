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
        descr=translate(
            "core.translationskel.tr_key.descr",
            "Translation key",
        ),
        searchable=True,
        unique=UniqueValue(UniqueLockMethod.SameValue, False,
                           "This translation key exist already"),
    )

    translations = StringBone(
        descr=translate(
            "core.translationskel.translations.descr",
            "Translations",
        ),
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
        descr=translate(
            "core.translationskel.translations_missing.descr",
            "Translation missing for language",
        ),
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
        descr=translate(
            "core.translationskel.default_text.descr",
            "Fallback value",
        ),
    )

    hint = StringBone(
        descr=translate(
            "core.translationskel.hint.descr",
            "Hint / Context (internal only)",
        ),
    )

    usage_filename = StringBone(
        descr=translate(
            "core.translationskel.usage_filename.descr",
            "Used and added from this file",
        ),
        readOnly=True,
    )

    usage_lineno = NumericBone(
        descr=translate(
            "core.translationskel.usage_lineno.descr",
            "Used and added from this lineno",
        ),
        readOnly=True,
    )

    usage_variables = StringBone(
        descr=translate(
            "core.translationskel.usage_variables.descr",
            "Receives these substitution variables",
        ),
        readOnly=True,
        multiple=True,
    )

    creator = SelectBone(
        descr=translate(
            "core.translationskel.creator.descr",
            "Creator",
        ),
        readOnly=True,
        values=Creator,
        defaultValue=Creator.USER,
    )

    @classmethod
    def toDB(cls, skelValues: SkeletonInstance, **kwargs) -> db.Key:
        # Ensure we have only lowercase keys
        skelValues["tr_key"] = skelValues["tr_key"].lower()
        return super().toDB(skelValues, **kwargs)

    @classmethod
    def preProcessSerializedData(cls, skelValues: SkeletonInstance, entity: db.Entity) -> db.Entity:
        # Backward-compatibility: re-add the key for viur-core < v3.6
        # TODO: Remove in ViUR4
        entity["key"] = skelValues["tr_key"]
        return super().preProcessSerializedData(skelValues, entity)


class Translation(List):
    kindName = KINDNAME

    def adminInfo(self):
        return {
            "name": translate("translations"),
            "icon": "translate",
            "display": "hidden" if len(conf.i18n.available_dialects) <= 1 else "default",
            "views": [
                {
                    "name": translate(
                        "core.translations.view.missing",
                        "Missing translations for {{lang}}",
                    )(lang=lang),
                    "filter": {
                        "translations_missing": lang,
                    },
                }
                for lang in conf.i18n.available_dialects
            ],
        }

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
