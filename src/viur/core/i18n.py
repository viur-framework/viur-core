import datetime
import logging
import time

import jinja2.ext as jinja2
from typing import List, Tuple, Union
from viur.core.config import conf
from viur.core import db, utils, languages, current
from pprint import pprint
systemTranslations = {}

# pprint = lambda *args, **kwargs: None


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
            self.translationCache = systemTranslations.get(self.key, {})

        try:
            lang = current.language.get()
        except Exception:
            # FIXME: when should this happen? we have a default value!
            logging.warning("Current has no lang", exc_info=True)
            return self.defaultText

        lang = conf.i18n.language_alias_map.get(lang, lang)

        # print(f'{self.translationCache = } // {self.key = } // {lang = }')

        return self.translationCache.get(lang, self.defaultText)

    def translate(self, **kwargs) -> str:
        res = str(self)
        for k, v in kwargs.items():
            res = res.replace("{{%s}}" % k, str(v))
        return res

    def __call__(self, *args, **kwargs):
        return self.translate(*args, **kwargs)


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
        if lastToken:  #TODO: what's this? what it is doing?
            print(f"final {lastToken = }")
            args.append(lastToken.value)
        if not 0 < len(args) <= 3:
            raise SyntaxError("Translation-Key missing or excess parameters!")
        args += [""] * (3 - len(args))
        args += [kwargs]
        trKey = args[0].lower()
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
    global systemTranslations

    lang_to_alias_map = {}

    pprint(f"{conf.i18n.language_alias_map = }")
    for alias_lang, translation_lang in conf.i18n.language_alias_map.items():
        lang_to_alias_map.setdefault(translation_lang, []).append(alias_lang)

    # Load translations from static languages module into systemTranslations
    for lang in dir(languages):
        if lang.startswith("__"):
            continue

        for tr_key, tr_value in getattr(languages, lang).items():
            systemTranslations.setdefault(tr_key, {})[lang] = tr_value

            for alias in lang_to_alias_map.get(lang, []): #TODO: why not resolve this in translate?
                systemTranslations[tr_key][alias] = tr_value

    pprint("invertMap")
    pprint(lang_to_alias_map)
    s = time.perf_counter()
    # Load translations from datastore into systemTranslations
    for tr in db.Query("viur-translations").run(55555):
        pprint(f"{tr = }")
        if not tr.get("key"):
            logging.error(f"translations entity {tr.key} has no key set")
            continue
        if tr and not isinstance(tr["translations"], dict):
            logging.error(f'translations entity {tr.key} has invalid translations set: {tr["translations"]}')
            continue
        trDict = {}
        for lang, translation in tr["translations"].items():
            if lang not in conf.i18n.available_languages:
                continue
            trDict[lang] = translation
            for alias in lang_to_alias_map.get(lang, []): # TODO: keep real accent translations?!
                trDict[alias] = translation

        pprint("trDict")
        pprint(trDict)
        # pprint(list(trDict.items())[:3])
        systemTranslations[tr["key"].lower()] = trDict

    e = time.perf_counter()
    print(f"time: {e - s}s")

    pprint("systemTranslations")
    # pprint(systemTranslations)
    pprint(list(systemTranslations.items())[:5])
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

"""
current.language.set("de")
print(f'{translate("yemen") = !s}')
print(f'{translate("CONTACT_FORM") = !s}')
print(f'{translate("contact_form") = !s}')
print(f'{translate("filter_amountresults") = !s}')
print(f'{translate("filter_amountresults").translate() = !s}')
print(f'{translate("filter_amountresults").translate() = !s}')
# """

