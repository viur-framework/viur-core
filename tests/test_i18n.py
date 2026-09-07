"""Tests for :func:`viur.core.i18n.migrate_translation`."""
import logging
from unittest import mock

from abstract import ViURTestCase


class TestMigrateTranslation(ViURTestCase):
    """A legacy entity must not take the instance down.

    ``migrate_translation`` is called synchronously by ``DatastoreSource.load`` for every
    translation entity without a name, and ``initializeTranslations`` re-raises whatever a
    source throws. The type check therefore has to validate rather than raise.
    """

    def _migrate(self, translation):
        """Run the migration on an entity carrying the given ``translation`` value.

        :return: The entity as it was handed to the skeleton.
        """
        from viur.core import db, i18n
        from viur.core.modules import translation as translation_module

        key = db.Key("viur-translations", "legacy")
        entity = db.Entity(key)
        entity["key"] = "some.key"
        entity["translation"] = translation

        skel = mock.MagicMock()
        with mock.patch.object(i18n.db, "get", return_value=entity), \
                mock.patch.object(translation_module, "TranslationSkel", return_value=skel):
            i18n.migrate_translation(key)

        skel.setEntity.assert_called_once()
        return skel.setEntity.call_args.args[0]

    def test_dict_translation_is_wrapped(self):
        entity = self._migrate({"de": "Hallo"})
        self.assertTrue(entity["translation"]["_viurLanguageWrapper_"])
        self.assertEqual("Hallo", entity["translation"]["de"])

    def test_missing_name_is_filled_from_key(self):
        entity = self._migrate({"de": "Hallo"})
        self.assertEqual("some.key", entity["name"])

    def test_non_dict_translation_is_logged_not_raised(self):
        with self.assertLogs(level=logging.ERROR) as logs:
            with self.assertRaises(TypeError):
                # A str has no place to put the wrapper marker in
                self._migrate("Hallo")
        self.assertTrue(any("translation is not a dict" in line for line in logs.output))
