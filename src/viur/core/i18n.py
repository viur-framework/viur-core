"""
This module provides translation, also known as internationalization -- short: i18n.

Project translations has to be stored in the datastore. There are only some
static translation tables in the viur-core to have some basics ones.

The viur-core own module "translation" (routed as _translation) provides an API
to manage these translation, for example in the vi-admin.

How to use translations?
First, make sure the languages are configured:
.. code-block:: python
    from viur.core.config import conf
    # These are the main languages (for which can translated values exits)
    # which should be available for the project
    conf.i18n.available_languages = = ["en", "de", "fr"]
    # These are some aliases for languages which should use the translated
    # values of a specific main langauges, but don't have own values.
    conf.i18n.language_alias_map = {
        "at": "de",  # Austria uses German
        "ch": "de",  # Switzerland uses German
        "be": "fr",  # Belgian uses France
        "us": "en",  # US uses English
    }

Now translations can be used

1. In python
.. code-block:: python
    from viur.core.i18n import translate
    # Just a key, the minimal cases
    print(translate("translation-key"))
    # provide also a default values, which will be used if there isn't a value
    # in the datastore set and a hint to provide some context.
    print(translate("translation-key", "the default value", "a hint"))
    # Use string interpolation with variables
    print(translate("hello", "Hello {{name}}!", "greet a user", name=current.user.get()["firstname"]))

2. In jinja
.. code-block:: jinja
    {# Use the ViUR translate extension, it can be compiled with the template,
       caches the translation values and is therefor efficient #}
    {% do translate "hello", "Hello {{name}}!", "greet a user", name="ViUR" %}

    {# But in some cases the key or interpolation-variables are dynamically
       and aren't available during template compilation.
       For this you can use the translate function: #}
    {{ translate("hello", "Hello {{name}}!", "greet a user", name=skel["firstname"]) }}


How to add translation
There are two ways how translations can be added:
1. Manually
With the vi-admin. Entries can be added manuell by creating a new skeleton and
filling out the key and values.
2. Automatically
This requires the enabled option add_missing_translations
.. code-block:: python

    from viur.core.config import conf
    conf.i18n.add_missing_translations = True

Now when an translation is printed and the key is unknown (because some just
added the output) an entry will be added to the datastore kind. Additionally
the defaultValue and hint will be filled out and the filename and lineno of
the place of usage in the code will be set in the Skeleton too.
That's the recommended way, because ViUR will collect all the information you
need and you have only to enter the translated values.
"""
# FIXME: grammar, rst syntax


import datetime
import logging
from pprint import pprint
from typing import List, Tuple, Union

import jinja2.ext as jinja2
import time

from viur.core import current, db, languages, tasks
from viur.core.config import conf

systemTranslations = {}
"""Memory storage for translation methods"""

KINDNAME = "viur-translations"
"""Kindname for the translations"""


class LanguageWrapper(dict):
    """
        Wrapper-class for a multi-language value.
        It's a dictionary, allowing accessing each stored language,
        but can also be used as a string, in which case it tries to
        guess the correct language.
    """

    def __init__(self, languages: Union[List[str], Tuple[str]]):
        super(LanguageWrapper, self).__init__()
        self.languages = languages

    def __str__(self) -> str:
        return str(self.resolve())

    def __bool__(self) -> bool:
        # Overridden to support if skel["bone"] tests in html render
        # (otherwise that test is always true as this dict contains keys)
        return bool(str(self))

    def resolve(self) -> Union[str, List[str]]:
        """
            Causes this wrapper to evaluate to the best language available for the current request.

            :returns: A item stored inside this instance or the empty string.
        """
        lang = current.language.get()
        if not lang:
            logging.warning(f"No lang set to current! {lang = }")
            lang = self.languages[0]
        else:
            lang = conf.i18n.language_alias_map.get(lang, lang)
        if (value := self.get(lang)) and str(value).strip():  # The users language is available :)
            return value
        else:  # We need to select another lang for him
            for lang in self.languages:
                if (value := self.get(lang)) and str(value).strip():
                    return value
        return ""


class translate:
    """
        This class is the replacement for the old translate() function provided by ViUR2.  This classes __init__
        takes the unique translation key (a string usually something like "user.auth_user_password.loginfailed" which
        uniquely defines this text fragment), a default text that will be used if no translation for this key has been
        added yet (in the projects default language) and a hint (an optional text that can convey context information
        for the persons translating these texts - they are not shown to the end-user). This class will resolve it's
        translations upfront, so the actual resolving (by casting this class to string) is fast. This resolves most
        translation issues with bones, which can now take an instance of this class as it's description/hints.
    """

    __slots__ = ["key", "defaultText", "hint", "translationCache"]

    def __init__(self, key: str, defaultText: str = None, hint: str = None):
        """
        :param key: The unique key defining this text fragment. Usually it's path/filename and a uniqe descriptor
            in that file
        :param defaultText:  The text to use if no translation has been added yet. While optional, it's recommended
            to set this, as we use the key instead if neither are available.
        :param hint: A text only shown to the person translating this text, as the key/defaultText may have different
            meanings in the target language.
        """
        super(translate, self).__init__()

        key = str(key)  # ensure key is a str
        self.key = key.lower()
        self.defaultText = defaultText or key
        self.hint = hint
        self.translationCache = None

    def __repr__(self) -> str:
        return "<translate object for %s>" % self.key

    def __str__(self) -> str:
        if self.translationCache is None:
            global systemTranslations

            import traceback
            traceback.print_stack()
            pprint(traceback.extract_stack())

            # for frame, line in traceback.walk_stack(None):
            #     print(f"{line=} // {frame=} // {frame.f_code} // {repr(frame)}")
            #     pprint({k: repr(getattr(frame, k))[:150] for k in dir(frame)})
            #     pprint({k: repr(getattr(frame.f_code, k))[:150] for k in dir(frame.f_code)})

            # import traceback
            # traceback.print_stack()
            # print(traceback.extract_stack())

            from viur.core.render.html.env.viur import translate as jinja_translate

            lineno = filename = None

            first = None
            is_jinja = False
            for frame, line in traceback.walk_stack(None):
                if first is None:
                    first = frame
                print(f"{line=} // {frame=} // {frame.f_code.co_name=} // {frame=}")
                if is_jinja and not frame.f_code.co_filename.endswith(".py"):
                    pprint({k: repr(getattr(frame, k))[:150] for k in dir(frame)})
                    pprint({k: repr(getattr(frame.f_code, k))[:150] for k in dir(frame.f_code)})
                    filename = frame.f_code.co_filename
                    lineno = line
                    break

                # if frame.f_code.co_filename.endswith("/render/html/env/viur.py") and frame.f_code.co_name == "translate":
                if frame.f_code == jinja_translate.__code__:
                    print("IS JINJA")
                    is_jinja = True
                    pprint({k: repr(getattr(frame, k))[:150] for k in dir(frame)})
                    pprint({k: repr(getattr(frame.f_code, k))[:150] for k in dir(frame.f_code)})

                print(f"{frame.f_code == jinja_translate.__code__ = }")
                print(f"{frame.f_code is jinja_translate.__code__ = }")
                print(f"{frame.f_code.co_code == jinja_translate.__code__ = }")
                print(f"{is_jinja = }")
                # print(f"{frame.f_code.co_code == jinja_translate}")

            if not is_jinja:
                lineno = first.f_lineno
                first = first.f_code.co_filename

            if self.key not in systemTranslations:
                add_missing_translation(
                    key=self.key,
                    hint=self.hint,
                    default_text=self.defaultText,
                    filename=filename,
                    lineno=lineno,
                )

            self.translationCache = systemTranslations.get(self.key, {})

        lang = current.language.get()
        lang = conf.i18n.language_alias_map.get(lang, lang)

        print(f'{self.translationCache = } // {self.key = } // {self.defaultText = } // {self.hint = } // {lang = }')

        if not (value := self.translationCache.get(lang)):
            return self.translationCache.get("_default_text_") or self.defaultText

        return str(self.translationCache.get(lang, self.defaultText))

    def translate(self, **kwargs) -> str:
        res = str(self)
        for k, v in kwargs.items():
            res = res.replace("{{%s}}" % k, str(v))
        return res

    def __call__(self, **kwargs):
        return self.translate(**kwargs)


class TranslationExtension(jinja2.Extension):
    """
        Default translation extension for jinja2 render.
        Use like {% translate "translationKey", "defaultText", "translationHint", replaceValue1="replacedText1" %}
        All except translationKey is optional. translationKey is the same Key supplied to _() before.
        defaultText will be printed if no translation is available.
        translationHint is a optional hint for anyone adding a now translation how/where that translation is used.
    """

    tags = {"translate"}

    def parse(self, parser):
        # Parse the translate tag
        global systemTranslations
        args = []
        kwargs = {}
        lineno = parser.stream.current.lineno
        filename = parser.stream.filename
        print(f"{parser.stream.current = }")
        print(f"{parser.stream.current.type = }")
        # print(f"{parser.stream.current.value = }")
        print(f"{parser.stream = }")
        print(f"{parser.stream.filename= }")
        # Parse arguments (args and kwargs) until the current block ends
        lastToken = None
        while parser.stream.current.type != 'block_end':
            print("while loop")
            lastToken = parser.parse_expression()
            print(f"{lastToken = }")
            print(f"{parser.stream.current = }")
            if parser.stream.current.type == "comma":  # It's an arg
                args.append(lastToken.value)
                next(parser.stream)  # Advance pointer
                lastToken = None
            elif parser.stream.current.type == "assign":
                next(parser.stream)  # Advance beyond =
                expr = parser.parse_expression()
                print(f"{expr = }")
                kwargs[lastToken.name] = expr.value
                if parser.stream.current.type == "comma":
                    next(parser.stream)
                elif parser.stream.current.type == "block_end":
                    lastToken = None
                    break
                else:
                    raise SyntaxError()
                lastToken = None
        if lastToken:  # TODO: what's this? what it is doing?
            print(f"final {lastToken = }")
            args.append(lastToken.value)
        if not 0 < len(args) <= 3:
            raise SyntaxError("Translation-Key missing or excess parameters!")
        args += [""] * (3 - len(args))
        args += [kwargs]
        trKey = args[0].lower()
        if trKey not in systemTranslations:
            add_missing_translation(
                key=trKey,
                hint=args[1],
                default_text=args[2],
                filename=filename,
                lineno=lineno,
                variables=list(kwargs.keys()),
            )

        trDict = systemTranslations.get(trKey, {})
        args = [jinja2.nodes.Const(x) for x in args]
        args.append(jinja2.nodes.Const(trDict))
        return jinja2.nodes.CallBlock(self.call_method("_translate", args), [], [], []).set_lineno(lineno)

    def _translate(self, key, defaultText, hint, kwargs, trDict, caller) -> str:
        """Perform the actual translation during render"""
        lng = current.language.get()
        lng = conf.i18n.language_alias_map.get(lng, lng)
        res = str(trDict.get(lng, defaultText))
        for k, v in kwargs.items():
            res = res.replace("{{%s}}" % k, str(v))
        return res


def initializeTranslations() -> None:
    """
        Fetches all translations from the datastore and populates the *systemTranslations* dictionary of this module.
        Currently, the translate-class will resolve using that dictionary; but as we expect projects to grow and
        accumulate translations that are no longer/not yet used, we plan to made the translation-class fetch it's
        translations directly from the datastore, so we don't have to allocate memory for unused translations.
    """
    # global systemTranslations
    start = time.perf_counter()
    # import viur_cli.deploy

    lang_to_alias_map = {}

    # pprint(f"{conf.i18n.language_alias_map = }")
    # for alias_lang, translation_lang in conf.i18n.language_alias_map.items():
    #     lang_to_alias_map.setdefault(translation_lang, []).append(alias_lang)

    # Load translations from static languages module into systemTranslations
    # If they're in the datastore, they will be overwritten below.
    for lang in dir(languages):
        if lang.startswith("__"):
            continue
        for tr_key, tr_value in getattr(languages, lang).items():
            systemTranslations.setdefault(tr_key, {})[lang] = tr_value

    # pprint("invertMap")
    # pprint(lang_to_alias_map)
    # Load translations from datastore into systemTranslations
    # for tr in db.Query(KINDNAME).iter():
    for tr in db.Query(KINDNAME).run(10_000):
        # pprint(f"{tr = }")

        if "tr_key" not in tr:
            logging.error(f"translations entity {tr.key} has no tr_key set --> Call migration")
            migrate_translation(tr.key)
            # Before the migration has run do a quick modification to get it loaded as is
            tr["tr_key"] = tr["key"] or tr.key.name
        if not tr.get("tr_key"):
            logging.error(f'translations entity {tr.key} has an empty {tr["tr_key"]=} set. Skipping.')
            continue
        if tr and not isinstance(tr["translations"], dict):
            logging.error(f'translations entity {tr.key} has invalid translations set: {tr["translations"]}. Skipping.')
            continue

        tr_dict = {
            "_default_text_": tr.get("default_text") or None,
        }
        for lang, translation in tr["translations"].items():
            if lang not in conf.i18n.available_languages:
                # Don't store unknown languages in the memory
                continue
            tr_dict[lang] = translation
        # pprint("tr_dict")
        # pprint(tr_dict)
        # pprint(list(tr_dict.items())[:3])
        systemTranslations[tr["tr_key"].lower()] = tr_dict

    end = time.perf_counter()
    print(f"time: {end - start}s")

    pprint("systemTranslations")
    # pprint(systemTranslations)
    # pprint(list(systemTranslations.items())[:5])
    # """
    current.language.set("de")
    print(f'{translate("yemen") = !s}')
    print(f'{translate("CONTACT_FORM") = !s}')
    print(f'{translate("contact_form") = !s}')
    print(f'{translate("filter_amountresults") = !s}')
    print(f'{translate("filter_amountresults").translate() = !s}')
    print(f'{translate("filter_amountresults").translate(current=7) = !s}')
    print(f'{translate("filter_amountresults").translate(current=7, total=42) = !s}')
    print(f'{translate("filter_amountresults")(current=7, total=42) = !s}')
    # """


@tasks.CallDeferred
@tasks.retry_n_times(20)
def add_missing_translation(
    key: str,
    hint: str | None = None,
    default_text: str | None = None,
    filename: str | None = None,
    lineno: int | None = None,
    variables: list[str] = [],
) -> None:
    from viur.core.modules.translation import TranslationSkel
    from viur.core.modules.translation import Creator

    entity = db.Query(KINDNAME).filter("tr_key =", key).getEntry()
    if entity is not None:
        logging.warning(f"Found an entity with tr_key={key}. "
                        f"Probably an other instance was faster.")
        return

    logging.info(f"Add missing translation {key}")
    skel = TranslationSkel()
    skel["tr_key"] = key
    skel["default_text"] = default_text
    skel["hint"] = hint
    skel["usage_filename"] = filename
    skel["usage_lineno"] = lineno
    skel["usage_variables"] = variables
    skel["creator"] = Creator.VIUR
    skel.toDB()


@tasks.CallDeferred
@tasks.retry_n_times(20)
def migrate_translation(
    key: db.Key,
) -> None:
    from viur.core.modules.translation import TranslationSkel

    logging.info(f"Migrate translation {key}")
    entity: db.Entity = db.Get(key)
    logging.debug(f"Source: {entity}")
    if "tr_key" not in entity:
        entity["tr_key"] = entity["key"] or key.name
    if "translation" in entity:
        if not isinstance(dict, entity["translation"]):
            logging.error("translation is not a dict?")
        entity["translation"]["_viurLanguageWrapper_"] = True
    skel = TranslationSkel()
    skel.setEntity(entity)
    skel["key"] = key
    logging.debug(f"Write: {skel}")
    try:
        skel.toDB()
    except ValueError as exc:
        logging.exception(exc)
        if "unique value" in exc.args[0] and "recently claimed" in exc.args[0]:
            logging.info(f"Delete duplicate entry {key}: {entity}")
            db.Delete(key)
        else:
            raise exc


localizedDateTime = translate("const_datetimeformat", "%a %b %d %H:%M:%S %Y", "Localized Time and Date format string")
localizedDate = translate("const_dateformat", "%m/%d/%Y", "Localized Date only format string")
localizedTime = translate("const_timeformat", "%H:%M:%S", "Localized Time only format string")
localizedAbbrevDayNames = {
    0: translate("const_day_0_short", "Sun", "Abbreviation for Sunday"),
    1: translate("const_day_1_short", "Mon", "Abbreviation for Monday"),
    2: translate("const_day_2_short", "Tue", "Abbreviation for Tuesday"),
    3: translate("const_day_3_short", "Wed", "Abbreviation for Wednesday"),
    4: translate("const_day_4_short", "Thu", "Abbreviation for Thursday"),
    5: translate("const_day_5_short", "Fri", "Abbreviation for Friday"),
    6: translate("const_day_6_short", "Sat", "Abbreviation for Saturday"),
}
localizedDayNames = {
    0: translate("const_day_0_long", "Sunday", "Sunday"),
    1: translate("const_day_1_long", "Monday", "Monday"),
    2: translate("const_day_2_long", "Tuesday", "Tuesday"),
    3: translate("const_day_3_long", "Wednesday", "Wednesday"),
    4: translate("const_day_4_long", "Thursday", "Thursday"),
    5: translate("const_day_5_long", "Friday", "Friday"),
    6: translate("const_day_6_long", "Saturday", "Saturday"),
}
localizedAbbrevMonthNames = {
    1: translate("const_month_1_short", "Jan", "Abbreviation for January"),
    2: translate("const_month_2_short", "Feb", "Abbreviation for February"),
    3: translate("const_month_3_short", "Mar", "Abbreviation for March"),
    4: translate("const_month_4_short", "Apr", "Abbreviation for April"),
    5: translate("const_month_5_short", "May", "Abbreviation for May"),
    6: translate("const_month_6_short", "Jun", "Abbreviation for June"),
    7: translate("const_month_7_short", "Jul", "Abbreviation for July"),
    8: translate("const_month_8_short", "Aug", "Abbreviation for August"),
    9: translate("const_month_9_short", "Sep", "Abbreviation for September"),
    10: translate("const_month_10_short", "Oct", "Abbreviation for October"),
    11: translate("const_month_11_short", "Nov", "Abbreviation for November"),
    12: translate("const_month_12_short", "Dec", "Abbreviation for December"),
}
localizedMonthNames = {
    1: translate("const_month_1_long", "January", "January"),
    2: translate("const_month_2_long", "February", "February"),
    3: translate("const_month_3_long", "March", "March"),
    4: translate("const_month_4_long", "April", "April"),
    5: translate("const_month_5_long", "May", "May"),
    6: translate("const_month_6_long", "June", "June"),
    7: translate("const_month_7_long", "July", "July"),
    8: translate("const_month_8_long", "August", "August"),
    9: translate("const_month_9_long", "September", "September"),
    10: translate("const_month_10_long", "October", "October"),
    11: translate("const_month_11_long", "November", "November"),
    12: translate("const_month_12_long", "December", "December"),
}


def localizedStrfTime(datetimeObj: datetime.datetime, format: str) -> str:
    """
        Provides correct localized names for directives like %a which don't get translated on GAE properly as we can't
        set the locale (for each request).
        This currently replaces %a, %A, %b, %B, %c, %x and %X.

        :param datetimeObj: Datetime-instance to call strftime on
        :param format: String containing the Format to apply.
        :returns: Date and time formatted according to format with correct localization
    """
    if "%c" in format:
        format = format.replace("%c", str(localizedDateTime))
    if "%x" in format:
        format = format.replace("%x", str(localizedDate))
    if "%X" in format:
        format = format.replace("%X", str(localizedTime))
    if "%a" in format:
        format = format.replace("%a", str(localizedAbbrevDayNames[int(datetimeObj.strftime("%w"))]))
    if "%A" in format:
        format = format.replace("%A", str(localizedDayNames[int(datetimeObj.strftime("%w"))]))
    if "%b" in format:
        format = format.replace("%b", str(localizedAbbrevMonthNames[int(datetimeObj.strftime("%m"))]))
    if "%B" in format:
        format = format.replace("%B", str(localizedMonthNames[int(datetimeObj.strftime("%m"))]))
    return datetimeObj.strftime(format)
