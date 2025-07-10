import enum
import fnmatch
import json
import logging
import os
import datetime
from deprecated.sphinx import deprecated
from viur.core import conf, db, utils, current, errors
from viur.core.decorators import exposed
from viur.core.bones import *
from viur.core.i18n import KINDNAME, initializeTranslations, systemTranslations, translate
from viur.core.prototypes.list import List
from viur.core.skeleton import Skeleton, ViurTagsSearchAdapter


class Creator(enum.Enum):
    VIUR = "viur"
    USER = "user"


class TranslationSkel(Skeleton):
    kindName = KINDNAME

    database_adapters = [
        ViurTagsSearchAdapter(max_length=256),
    ]

    name = StringBone(
        descr=translate(
            "viur.core.translationskel.name.descr",
            "Translation key",
        ),
        searchable=True,
        escape_html=False,
        readOnly=True,  # this is only readOnly=False on add!
        vfunc=lambda value: translate(
            "viur.core.translationskel.name.vfunc",
            "The translation key may not contain any upper-case characters."
        ) if any(ch.isupper() for ch in value) else None,
        unique=UniqueValue(
            UniqueLockMethod.SameValue,
            False,
            "This translation key already exists"
        ),
    )

    # FIXME: Remove with VIUR4
    tr_key = StringBone(
        descr="Translation key (OLD - DEPRECATED!)",
        escape_html=False,
        readOnly=True,
        visible=False,
    )

    translations = StringBone(
        descr=translate(
            "viur.core.translationskel.translations.descr",
            "Translations",
        ),
        searchable=True,
        languages=conf.i18n.available_dialects,
        escape_html=False,
        max_length=1024,
        params={
            "tooltip": translate(
                "viur.core.translationskel.translations.tooltip",
                "The languages {{main}} are required,\n {{accent}} can be filled out"
            )(main=", ".join(conf.i18n.available_languages),
              accent=", ".join(conf.i18n.language_alias_map.keys())),
        }
    )

    translations_missing = SelectBone(
        descr=translate(
            "viur.core.translationskel.translations_missing.descr",
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
            "viur.core.translationskel.default_text.descr",
            "Fallback value",
        ),
        escape_html=False,
    )

    hint = StringBone(
        descr=translate(
            "viur.core.translationskel.hint.descr",
            "Hint / Context (internal only)",
        ),
    )

    usage_filename = StringBone(
        descr=translate(
            "viur.core.translationskel.usage_filename.descr",
            "Used and added from this file",
        ),
        readOnly=True,
    )

    usage_lineno = NumericBone(
        descr=translate(
            "viur.core.translationskel.usage_lineno.descr",
            "Used and added from this lineno",
        ),
        readOnly=True,
    )

    usage_variables = StringBone(
        descr=translate(
            "viur.core.translationskel.usage_variables.descr",
            "Receives these substitution variables",
        ),
        readOnly=True,
        multiple=True,
    )

    creator = SelectBone(
        descr=translate(
            "viur.core.translationskel.creator.descr",
            "Creator",
        ),
        readOnly=True,
        values=Creator,
        defaultValue=Creator.USER,
    )

    public = BooleanBone(
        descr=translate(
            "viur.core.translationskel.public.descr",
            "Is this translation public?",
        ),
        defaultValue=False,
    )

    @classmethod
    def read(cls, skel, *args, **kwargs):
        if skel := super().read(skel, *args, **kwargs):
            if skel["tr_key"]:
                skel["name"] = skel["tr_key"]
                skel["tr_key"] = None

        return skel

    @classmethod
    def write(cls, skel, **kwargs):
        # Create the key from the name on initial write!
        if not skel["key"]:
            skel["key"] = db.Key(KINDNAME, skel["name"])

        return super().write(skel, **kwargs)


class Translation(List):
    """
    The Translation module is a system module used by the ViUR framework for its internationalization capabilities.
    """

    kindName = KINDNAME

    def adminInfo(self):
        return {
            "name": translate("translations"),
            "icon": "translate",
            "display": "hidden" if len(conf.i18n.available_dialects) <= 1 else "default",
            "views": [
                {
                    "name": translate(
                        "viur.core.translations.view.system",
                        "ViUR System translations",
                    ),
                    "filter": {
                        "name$lk": "viur.",
                    }
                },
                {
                    "name": translate(
                        "viur.core.translations.view.public",
                        "Public translations",
                    ),
                    "filter": {
                        "public": True,
                    }
                }
            ] + [
                {
                    "name": translate(
                        "viur.core.translations.view.missing",
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

    def addSkel(self):
        """
        Returns a custom TranslationSkel where the name is editable.
        The name becomes part of the key.
        """
        skel = super().addSkel().ensure_is_cloned()
        skel.name.readOnly = False
        skel.name.required = True
        return skel

    cloneSkel = addSkel

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
            and self._last_reload - utils.utcNow() < datetime.timedelta(minutes=10)
        ):
            # debounce: translations has been reload recently, skip this
            return None

        logging.info("Reload translations")
        # TODO: this affects only the current instance
        self._last_reload = utils.utcNow()
        systemTranslations.clear()
        initializeTranslations()

    _last_reload = None  # Cut my strings into pieces, this is my last reload...

    @exposed
    def dump(
        self,
        *,
        pattern: list[str] | None = None,
        language: list[str] | None = None,
    ) -> dict[str, dict[str, str]]:
        """
        Dumps translations as JSON.

        :param pattern: Optional, provide fnmatch-style translation key filter patterns of the translations wanted.
        :param language: Allows to request a specific language.
            By default, the language of the current request is used.

        :return: A dictionary with translations as JSON. Structure: ``{language: {key: value, ...}, ...}``

        Example calls:

        - `/json/_translation/dump?pattern=viur.*` get viur.*-translations for current language
        - `/json/_translation/dump?pattern=viur.*&language=en` for english translations
        - `/json/_translation/dump?pattern=viur.*&language=en&language=de` for english and german translations
        - `/json/_translation/dump?pattern=viur.*&language=*` for all available language
        """
        if not utils.string.is_prefix(self.render.kind, "json"):
            raise errors.BadRequest("Can only use this function on JSON-based renders")

        current.request.get().response.headers["Content-Type"] = "application/json"

        if (
            not (conf.debug.disable_cache and current.request.get().disableCache)
            and any(os.getenv("HTTP_HOST", "") in dlm for dlm in conf.i18n.domain_language_mapping)
        ):
            # cache it 7 days
            current.request.get().response.headers["Cache-Control"] = f"public, max-age={7 * 24 * 60 * 60}"

        if language:
            if len(language) == 1 and language[0] == "*":
                language = conf.i18n.available_dialects
        else:
            language = [current.language.get()]

        return json.dumps({  # type: ignore
            lang: {
                name: str(translate(name, force_lang=lang))
                for name, values in systemTranslations.items()
                if (conf.i18n.dump_can_view(name) or values.get("_public_"))
                and (not pattern or any(fnmatch.fnmatch(name, pat) for pat in pattern))
            }
            for lang in language
        })

    @exposed
    @deprecated(
        version="3.7.10",
        reason="Function renamed. Use 'dump' function as alternative implementation.",
    )
    def get_public(self, *, languages: list[str] = [], **kwargs):
        return self.dump(language=languages, **kwargs)


Translation.json = True
