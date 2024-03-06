"""
ViUR utility functions regarding string processing.
"""
import re
import secrets
import string
import warnings


def random(length: int = 13) -> str:
    """
    Return a string containing random characters of given *length*.
    It's safe to use this string in URLs or HTML.
    Because we use the secrets module it could be used for security purposes as well

    :param length: The desired length of the generated string.

    :returns: A string with random characters of the given length.
    """
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))


# String base mapping
__STRING_ESCAPE_MAPPING = {
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
    "(": "&#40;",
    ")": "&#41;",
    "=": "&#61;",
    "\n": " ",
    "\0": "",
}

# Translation table for string escaping
__STRING_ESCAPE_TRANSTAB = str.maketrans(__STRING_ESCAPE_MAPPING)

# Lookup-table for string unescaping
__STRING_UNESCAPE_MAPPING = {v: k for k, v in __STRING_ESCAPE_MAPPING.items() if v}


def escape(val: str, max_length: int | None = 254, maxLength: int | None = None) -> str:
    """
        Quotes special characters from a string and removes "\\\\0".
        It shall be used to prevent XSS injections in data.

        :param val: The value to be escaped.
        :param max_length: Cut-off after max_length characters. None or 0 means "unlimited".

        :returns: The quoted string.
    """
    # fixme: Remove in viur-core >= 4
    if maxLength is not None and max_length == 254:
        warnings.warn("'maxLength' is deprecated, please use 'max_length'", DeprecationWarning)
        max_length = maxLength

    res = str(val).strip().translate(__STRING_ESCAPE_TRANSTAB)

    if max_length:
        return res[:max_length]

    return res


def unescape(val: str) -> str:
    """
        Unquotes characters formerly escaped by `escape`.

        :param val: The value to be unescaped.
        :param max_length: Optional cut-off after max_length characters. \
            A value of None or 0 means "unlimited".

        :returns: The unquoted string.
    """
    def __escape_replace(re_match):
        # In case group 2 is matched, search for its escape sequence
        if find := re_match.group(2):
            find = f"&#{find};"
        else:
            find = re_match.group(0)

        return __STRING_UNESCAPE_MAPPING.get(find) or re_match.group(0)

    return re.sub(r"&(\w{2,4}|#0*(\d{2}));", __escape_replace, str(val).strip())


def is_prefix(name: str, prefix: str, delimiter: str = ".") -> bool:
    """
    Utility function to check if a given name matches a prefix,
    which defines a specialization, delimited by `delimiter`.

    In ViUR, modules, bones, renders, etc. provide a kind or handler
    to classify or subclassify the specific object. To securitly
    check for a specific type, it is either required to ask for the
    exact type or if its prefixed by a path delimited normally by
    dots.

    Example:

    .. code-block:: python
        handler = "tree.file.special"
        utils.string.is_prefix(handler, "tree")  # True
        utils.string.is_prefix(handler, "tree.node")  # False
        utils.string.is_prefix(handler, "tree.file")  # True
        utils.string.is_prefix(handler, "tree.file.special")  # True
    """
    return name == prefix or name.startswith(prefix + delimiter)
