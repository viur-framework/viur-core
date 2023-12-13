import copy

from viur.core import Module


class InstancedModule:
    """InstancedModule is a base class for modules, which can be passed as instance to the viur-core.

    Normally, the viur-core expects classes from modules and instantiates them during setup.
    However, there are cases where you want to pass already instantiated
    classes, i.e. module instances, to the core. For example, to integrate
    plugins. This is where this base class comes into play. If it is included
    as an ADDITIONAL base class to the module class, the viur-core accepts an
    instance of this class. The class itself is then no longer
    instantiated in the core.

    In order to preserve the well-known ViUR module concept, this class
    overwrites the __init__ method so that it behaves like a classic object
    constructor. The __call__ method then takes on the role of the
    conventional __init__ module.
    However, as each render requires its own module instance, as the render
    itself is then referenced to this instance via the "render" attribute,
    several instances are required. Therefore, a copy of the module instance
    is created using the internal method `_viur_clone`. This can be changed
    if necessary. A shadow-copy is created here by default.

    Here an example:

    .. code-block:: python

        from viur.core.prototypes import List
        from viur.core.prototypes.instanced_module import InstancedModule


        class MyModule(InstancedModule, List):
            def __init__(self, configuration):
                self.configuration = configuration


        my_module = MyModule(
            configuration=...
        )

    As you can see, the configuration parameter is set from outside and not
    in the class. This may seem a bit strange here, but now imagine that the
    class definition `MyModule` is not within the same file but in an imported
    pip package. Then this instantiation is much easier than using a subclass.
    """

    def __init__(self, *args, **kwargs):
        """Overwrite the Module.__init__ and do nothing

        Can be overwritten as needed, e.g. to assign instance attributes.
        """
        object.__init__(self)

    def __call__(self, moduleName: str, modulePath: str, *args, **kwargs) -> "InstancedModule":
        """Do the instance initialisation

        Take the role of Module.__init__ (and call it).
        """
        if modulePath == f"/{moduleName}":
            # For the default renderer we use the original instance
            instance = self
        else:
            # For other renderer we use a copy
            instance = self._viur_clone()
        Module.__init__(instance, moduleName, modulePath, *args, **kwargs)
        return instance

    def _viur_clone(self):
        """Creates a copy for non-standard renderers.

        Since viur keeps one instance per render. Can be overwritten if desired.
        """
        return copy.copy(self)
