import datetime
import logging
import typing as t
import urllib.parse
import warnings
from collections.abc import Iterable

from viur.core import current, db
from viur.core.config import conf
from deprecated.sphinx import deprecated
from . import json, parse, string  # noqa: used by external imports


def utcNow() -> datetime.datetime:
    """
    Returns an actual timestamp with UTC timezone setting.
    """
    return datetime.datetime.now(datetime.timezone.utc)


def seoUrlToEntry(module: str,
                  entry: t.Optional["SkeletonInstance"] = None,
                  skelType: t.Optional[str] = None,
                  language: t.Optional[str] = None) -> str:
    """
    Return the seo-url to a skeleton instance or the module.

    :param module: The module name.
    :param entry: A skeleton instance or None, to get the path to the module.
    :param skelType: # FIXME: Not used
    :param language: For which language.
        If None, the language of the current request is used.
    :return: The path (with a leading /).
    """
    from viur.core import conf
    pathComponents = [""]
    if language is None:
        language = current.language.get()
    if conf.i18n.language_method == "url":
        pathComponents.append(language)
    if module in conf.i18n.language_module_map and language in conf.i18n.language_module_map[module]:
        module = conf.i18n.language_module_map[module][language]
    pathComponents.append(module)
    if not entry:
        return "/".join(pathComponents)
    else:
        try:
            currentSeoKeys = entry["viurCurrentSeoKeys"]
        except:
            return "/".join(pathComponents)
        if language in (currentSeoKeys or {}):
            pathComponents.append(str(currentSeoKeys[language]))
        elif "key" in entry:
            key = entry["key"]
            if isinstance(key, str):
                try:
                    key = db.Key.from_legacy_urlsafe(key)
                except:
                    pass
            pathComponents.append(str(key.id_or_name) if isinstance(key, db.Key) else str(key))
        elif "name" in dir(entry):
            pathComponents.append(str(entry.name))
        return "/".join(pathComponents)


def seoUrlToFunction(module: str, function: str, render: t.Optional[str] = None) -> str:
    from viur.core import conf
    lang = current.language.get()
    if module in conf.i18n.language_module_map and lang in conf.i18n.language_module_map[module]:
        module = conf.i18n.language_module_map[module][lang]
    if conf.i18n.language_method == "url":
        pathComponents = ["", lang]
    else:
        pathComponents = [""]
    targetObject = conf.main_resolver
    if module in targetObject:
        pathComponents.append(module)
        targetObject = targetObject[module]
    if render and render in targetObject:
        pathComponents.append(render)
        targetObject = targetObject[render]
    if function in targetObject:
        func = targetObject[function]
        if func.seo_language_map and lang in func.seo_language_map:
            pathComponents.append(func.seo_language_map[lang])
        else:
            pathComponents.append(function)
    return "/".join(pathComponents)


@deprecated(version="3.8.0", reason="Use 'db.normalize_key' instead")
def normalizeKey(key: t.Union[None, db.Key]) -> t.Union[None, db.Key]:
    """
        Normalizes a datastore key (replacing _application with the current one)

        :param key: Key to be normalized.

        :return: Normalized key in string representation.
    """
    db.normalize_key(key)


def ensure_iterable(
    obj: t.Any,
    *,
    test: t.Optional[t.Callable[[t.Any], bool]] = None,
    allow_callable: bool = True,
) -> t.Iterable[t.Any]:
    """
    Ensures an object to be iterable.

    An additional test can be provided to check additionally.

    If the object is not considered to be iterable, a tuple with the object is returned.
    """
    if allow_callable and callable(obj):
        obj = obj()

    if not isinstance(obj, str) and isinstance(obj, Iterable):  # uses collections.abc.Iterable
        if test is None or test(obj):
            return obj  # return the obj, which is an iterable

        return ()  # empty tuple

    elif obj is None or (isinstance(obj, str) and not obj):
        return ()  # empty tuple

    return obj,  # return a tuple with the obj


def build_content_disposition_header(
    filename: str,
    *,
    attachment: bool = False,
    inline: bool = False,
) -> str:
    """
    Build a Content-Disposition header with UTF-8 support and ASCII fallback.

    Generates a properly formatted `Content-Disposition` header value, including
    both a fallback ASCII filename and a UTF-8 encoded filename using RFC 5987.

    Set either `attachment` or `inline` to control content disposition type.
    If both are False, the header will omit disposition type (not recommended).

    Example:
        filename = "Änderung.pdf" ➜
        'attachment; filename="Anderung.pdf"; filename*=UTF-8\'\'%C3%84nderung.pdf'

    :param filename: The desired filename for the content.
    :param attachment: Whether to mark the content as an attachment.
    :param inline: Whether to mark the content as inline.
    :return: A `Content-Disposition` header string.
    """
    if attachment and inline:
        raise ValueError("Only one of 'attachment' or 'inline' may be True.")

    fallback = string.normalize_ascii(filename)
    quoted_utf8 = urllib.parse.quote_from_bytes(filename.encode("utf-8"))

    content_disposition = "; ".join(
        item for item in (
            "attachment" if attachment else None,
            "inline" if inline else None,
            f'filename="{fallback}"' if filename else None,
            f'filename*=UTF-8\'\'{quoted_utf8}' if filename else None,
        ) if item
    )

    return content_disposition


# DEPRECATED ATTRIBUTES HANDLING
__UTILS_CONF_REPLACEMENT = {
    "projectID": "viur.instance.project_id",
    "isLocalDevelopmentServer": "viur.instance.is_dev_server",
    "projectBasePath": "viur.instance.project_base_path",
    "coreBasePath": "viur.instance.core_base_path"
}

__UTILS_NAME_REPLACEMENT = {
    "currentLanguage": ("current.language", current.language),
    "currentRequest": ("current.request", current.request),
    "currentRequestData": ("current.request_data", current.request_data),
    "currentSession": ("current.session", current.session),
    "downloadUrlFor": ("conf.main_app.file.create_download_url", lambda: conf.main_app.file.create_download_url),
    "escapeString": ("utils.string.escape", string.escape),
    "generateRandomString": ("utils.string.random", string.random),
    "getCurrentUser": ("current.user.get", current.user.get),
    "is_prefix": ("utils.string.is_prefix", string.is_prefix),
    "parse_bool": ("utils.parse.bool", parse.bool),
    "srcSetFor": ("conf.main_app.file.create_src_set", lambda: conf.main_app.file.create_src_set),
}


def __getattr__(attr):
    if replace := __UTILS_CONF_REPLACEMENT.get(attr):
        msg = f"Use of `utils.{attr}` is deprecated; Use `conf.{replace}` instead!"
        warnings.warn(msg, DeprecationWarning, stacklevel=3)
        logging.warning(msg, stacklevel=3)
        return conf[replace]

    if replace := __UTILS_NAME_REPLACEMENT.get(attr):
        msg = f"Use of `utils.{attr}` is deprecated; Use `{replace[0]}` instead!"
        warnings.warn(msg, DeprecationWarning, stacklevel=3)
        logging.warning(msg, stacklevel=3)
        res = replace[1]
        if isinstance(res, t.Callable):
            res = res()
        return res

    return super(__import__(__name__).__class__).__getattribute__(attr)
