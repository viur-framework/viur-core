from typing import Callable, Union

__jinjaGlobals_ = {}
__jinjaFilters_ = {}
__jinjaTests_ = {}
__jinjaExtensions_ = []


def getGlobalFunctions():
    return __jinjaGlobals_


def getGlobalFilters():
    return __jinjaFilters_


def getGlobalTests():
    return __jinjaTests_


def getGlobalExtensions():
    return __jinjaExtensions_


def jinjaGlobalFunction(f):
    """
    Decorator, marks a function as a Jinja2 global.
    """
    __jinjaGlobals_[f.__name__] = f
    return f


def jinjaGlobalFilter(f):
    """
    Decorator, marks a function as a Jinja2 filter.
    """
    __jinjaFilters_[f.__name__] = f
    return f


def jinjaGlobalTest(func_or_alias: Union[Callable, str]) -> Callable:
    """
    Decorator, marks a function as a Jinja2 test.

    To avoid name conflicts you can call the decorator
    with an alias as first argument.
    Otherwise, the test will be registered under the function name.

    Example:
        >>> from viur.core.render.html import jinjaGlobalTest
        >>> # @jinjaGlobalTest  # available under "positive_number"
        >>> @jinjaGlobalTest("positive")  # available under "positive"
        >>> def positive_number(render, value):
        >>>     return isinstance(value, int) and value > 0
    """
    if callable(func_or_alias):  # is func
        __jinjaTests_[func_or_alias.__name__] = func_or_alias
        return func_or_alias

    elif isinstance(func_or_alias, str):  # is alias
        def wrapper(func):
            __jinjaTests_[func_or_alias] = func
            return func

        return wrapper

    else:
        raise TypeError(
            f"jinjaGlobalTest must be called with a function (used as decorator) "
            f"or a string (alias). But got {type(func_or_alias)}."
        )


def jinjaGlobalExtension(ext):
    """
    Function for activating extensions in Jinja2.
    """
    if ext not in __jinjaExtensions_:
        __jinjaExtensions_.append(ext)
    return ext
