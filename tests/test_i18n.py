"""Tests for the translation migration and loading in :mod:`viur.core.i18n`."""
import logging
from unittest import mock

from abstract import ViURTestCase


def _skeleton_search_path():
    """Make ``TranslationSkel`` importable, see :mod:`tests.modules.test_user_app_login`."""
    from viur.core.config import conf
    if "/src/viur/core/" not in conf.skeleton_search_path:
        conf.skeleton_search_path = list(conf.skeleton_search_path) + ["/src/viur/core/"]


class TestMigrateTranslation(ViURTestCase):
    """A pre-3.6 entity stores the texts as a plain ``{lang: text}`` dict.

    ``TranslationSkel.translations`` is a multi-language bone, whose serialized form is a
    dict carrying ``_viurLanguageWrapper_``. Without that marker
    ``BaseBone.unserialize`` cannot tell the languages apart and puts the whole dict into
    the main language; ``translations_missing`` (``compute=OnWrite``) reads the bone during
    ``write()``, so the migration would persist exactly that.
    """

    def setUp(self) -> None:
        super().setUp()
        # Importing viur.core installs the ViURDefaultLogger and replaces the root
        # handlers. Inside an assertLogs block that would drop its capture handler, so the
        # import has to happen before any test method runs.
        from viur.core import bones, i18n  # noqa: F401

    def _migrate(self, entity_fields: dict):
        """Run the migration on an entity built from the given fields.

        :return: Tuple of the entity as handed to the skeleton, or None when the migration
            skipped it, and the mock that replaced ``TranslationSkel``.
        """
        from viur.core import bones, db  # noqa: F401  (import order, see project memory)
        from viur.core import i18n
        from viur.core.modules import translation as translation_module

        key = db.Key("viur-translations", "legacy")
        entity = db.Entity(key)
        for name, value in entity_fields.items():
            entity[name] = value

        skel = mock.MagicMock()
        with mock.patch.object(i18n.db, "get", return_value=entity), \
                mock.patch.object(translation_module, "TranslationSkel", return_value=skel):
            i18n.migrate_translation(key, _call_deferred=False)

        if not skel.setEntity.called:
            return None, skel
        return skel.setEntity.call_args.args[0], skel

    def test_legacy_dict_gets_the_language_wrapper_marker(self):
        entity, _ = self._migrate({"key": "some.key", "translations": {"de": "Hallo", "en": "Hello"}})
        self.assertTrue(entity["translations"]["_viurLanguageWrapper_"])
        self.assertEqual("Hallo", entity["translations"]["de"])
        self.assertEqual("Hello", entity["translations"]["en"])

    def test_missing_name_is_filled_from_key(self):
        entity, _ = self._migrate({"key": "some.key", "translations": {"en": "Hello"}})
        self.assertEqual("some.key", entity["name"])

    def test_already_migrated_entity_is_left_alone(self):
        translations = {"en": "Hello", "_viurLanguageWrapper_": True}
        entity, _ = self._migrate({"key": "some.key", "name": "some.key", "translations": translations})
        self.assertEqual(translations, dict(entity["translations"]))

    def test_entity_without_translations_is_skipped(self):
        with self.assertLogs(level=logging.ERROR) as logs:
            entity, skel = self._migrate({"key": "some.key"})
        self.assertIsNone(entity)
        skel.write.assert_not_called()
        self.assertTrue(any("is not a dict" in line for line in logs.output))

    def test_non_dict_translations_is_skipped(self):
        with self.assertLogs(level=logging.ERROR) as logs:
            entity, skel = self._migrate({"key": "some.key", "translations": "Hello"})
        self.assertIsNone(entity)
        skel.write.assert_not_called()
        self.assertTrue(any("is not a dict" in line for line in logs.output))


class TestMigratedEntityUnserializes(ViURTestCase):
    """The migrated entity has to keep its languages apart in the skeleton."""

    def _translations_of(self, stored: dict) -> dict:
        """Unserialize a stored ``translations`` value through a real TranslationSkel."""
        from viur.core import bones, db  # noqa: F401
        _skeleton_search_path()
        from viur.core.modules.translation import TranslationSkel

        entity = db.Entity(db.Key("viur-translations", "legacy"))
        entity["key"] = "some.key"
        entity["translations"] = stored

        skel = TranslationSkel()
        skel.setEntity(entity)
        return skel["translations"]

    def test_without_marker_the_whole_dict_lands_in_one_language(self):
        """The state this migration exists to get out of -- kept as the contrast."""
        main_lang = self._main_language()
        result = self._translations_of({"de": "Hallo", "en": "Hello"})
        self.assertEqual(str({"de": "Hallo", "en": "Hello"}), result[main_lang])

    def test_with_marker_each_language_keeps_its_own_text(self):
        result = self._translations_of({"de": "Hallo", "en": "Hello", "_viurLanguageWrapper_": True})
        for lang, text in (("de", "Hallo"), ("en", "Hello")):
            if lang in result:
                self.assertEqual(text, result[lang])

    @staticmethod
    def _main_language() -> str:
        from viur.core import bones  # noqa: F401
        _skeleton_search_path()
        from viur.core.modules.translation import TranslationSkel
        return TranslationSkel().translations.languages[0]


class TestDatastoreSourceLoad(ViURTestCase):
    """One unusable entity must not abort the whole load.

    ``initializeTranslations`` re-raises whatever a source throws, so a KeyError here
    takes the instance down at startup.
    """

    def setUp(self) -> None:
        super().setUp()
        # Importing viur.core installs the ViURDefaultLogger and replaces the root
        # handlers. Inside an assertLogs block that would drop its capture handler, so the
        # import has to happen before any test method runs.
        from viur.core import bones, i18n  # noqa: F401

    def _load(self, entities: list[dict]) -> dict:
        from viur.core import bones, db  # noqa: F401
        from viur.core import i18n

        built = []
        for idx, fields in enumerate(entities):
            entity = db.Entity(db.Key("viur-translations", f"e{idx}"))
            for name, value in fields.items():
                entity[name] = value
            built.append(entity)

        query = mock.MagicMock()
        query.run.return_value = built
        with mock.patch.object(i18n.db, "Query", return_value=query), \
                mock.patch.object(i18n, "migrate_translation"):
            return i18n.DatastoreSource().load()

    def test_entity_without_translations_is_skipped(self):
        with self.assertLogs(level=logging.ERROR):
            res = self._load([{"name": "broken.key"}])
        self.assertEqual({}, res)

    def test_usable_entities_survive_a_broken_one(self):
        with self.assertLogs(level=logging.ERROR):
            res = self._load([
                {"name": "broken.key"},
                {"name": "good.key", "translations": {"en": "Hello"}},
            ])
        self.assertIn("good.key", res)
        self.assertEqual("Hello", res["good.key"]["en"])
