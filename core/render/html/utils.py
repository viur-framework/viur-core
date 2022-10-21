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


def jinjaGlobalTest(f):
    """
    Decorator, marks a function as a Jinja2 test.

    The method name can start with "test_" to avoid name conflicts.
    """
    __jinjaTests_[f.__name__.lstrip("test_")] = f
    return f


def jinjaGlobalExtension(ext):
    """
    Function for activating extensions in Jinja2.
    """
    if ext not in __jinjaExtensions_:
        __jinjaExtensions_.append(ext)
    return ext
