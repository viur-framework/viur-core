from abstract import ViURTestCase

# Packages whose __all__ is part of the public surface and must therefore be importable via *.
STAR_IMPORTABLE = (
    "viur.core.render.json",
    "viur.core.skeleton",
)


class TestStarImports(ViURTestCase):
    """__all__ has to hold names, not the objects themselves - otherwise `import *` raises."""

    def test_star_import_works(self):
        for module_name in STAR_IMPORTABLE:
            with self.subTest(module=module_name):
                namespace = {}
                exec(f"from {module_name} import *", namespace)

    def test_all_entries_are_strings(self):
        import importlib
        for module_name in STAR_IMPORTABLE:
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                for entry in module.__all__:
                    self.assertIsInstance(entry, str, f"{module_name}.__all__ holds {entry!r}")

    def test_all_entries_exist_on_the_module(self):
        import importlib
        for module_name in STAR_IMPORTABLE:
            module = importlib.import_module(module_name)
            for name in module.__all__:
                with self.subTest(module=module_name, name=name):
                    self.assertTrue(hasattr(module, name), f"{module_name}.{name} does not exist")
