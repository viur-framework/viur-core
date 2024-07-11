import logging
import typing as t
import warnings
import datetime
from . import string, parse, json  # noqa: used by external imports
from viur.core import current, db
from viur.core.config import conf


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


def normalizeKey(key: t.Union[None, 'db.KeyClass']) -> t.Union[None, 'db.KeyClass']:
    """
        Normalizes a datastore key (replacing _application with the current one)

        :param key: Key to be normalized.

        :return: Normalized key in string representation.
    """
    if key is None:
        return None
    if key.parent:
        parent = normalizeKey(key.parent)
    else:
        parent = None
    return db.Key(key.kind, key.id_or_name, parent=parent)


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
    "downloadUrlFor": ("modules.file.File.create_download_url", "viur.core.modules.file.File.create_download_url"),
    "escapeString": ("utils.string.escape", string.escape),
    "generateRandomString": ("utils.string.random", string.random),
    "getCurrentUser": ("current.user.get", current.user.get),
    "is_prefix": ("utils.string.is_prefix", string.is_prefix),
    "parse_bool": ("utils.parse.bool", parse.bool),
    "srcSetFor": ("modules.file.File.create_src_set", "viur.core.modules.file.File.create_src_set"),
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

        ret = replace[1]

        # When this is a string, try to resolve by dynamic import
        if isinstance(ret, str):
            mod, item, attr = ret.rsplit(".", 2)
            mod = __import__(mod, fromlist=(item,))
            item = getattr(mod, item)
            ret = getattr(item, attr)

        return ret

    return super(__import__(__name__).__class__).__getattribute__(attr)
