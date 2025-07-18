import types

from abstract import ViURTestCase

OLD_MEMBERS = [
    "admin.name",
    "admin.logo",
    "admin.login.background",
    "admin.login.logo",
    "admin.color.primary",
    "admin.color.secondary",
    "viur.accessRights",
    "viur.availableLanguages",
    "viur.bone.boolean.str2true",
    "viur.cacheEnvironmentKey",
    "viur.compatibility",
    # "viur.contentSecurityPolicy", # removed this one, was not in use (we had it twice)
    "viur.debug.trace",
    "viur.debug.trace_exceptions",
    "viur.debug.trace_external_call_routing",
    "viur.debug.trace_internal_call_routing",
    "viur.debug.skeleton.fromClient",
    "viur.defaultLanguage",
    "viur.dev_server_cloud_logging",
    "viur.disable_cache",
    "viur.domainLanguageMapping",
    "viur.email.logRetention",
    "viur.email.transportClass",
    "viur.email.sendFromLocalDevelopmentServer",
    "viur.email.recipientOverride",
    "viur.email.senderOverride",
    "viur.email.admin_recipients",
    "viur.errorHandler",
    "viur.static.embedSvg.path",
    "viur.forceSSL",
    "viur.file.hmacKey",
    "viur.file.derivers",
    "viur.instance.app_version",
    "viur.instance.core_base_path",
    "viur.instance.is_dev_server",
    "viur.instance.project_base_path",
    "viur.instance.project_id",
    "viur.instance.version_hash",
    "viur.languageAliasMap",
    "viur.languageMethod",
    "viur.languageModuleMap",
    "viur.mainApp",
    "viur.mainResolver",
    "viur.maxPasswordLength",
    "viur.maxPostParamsCount",
    "viur.moduleconf.admin_info",
    "viur.script.admin_info",
    "viur.noSSLCheckUrls",
    "viur.otp.issuer",
    "viur.render.html.downloadUrlExpiration",
    "viur.render.json.downloadUrlExpiration",
    "viur.request_preprocessor",
    "viur.search_valid_chars",
    "viur.security.contentSecurityPolicy",
    "viur.security.referrer_policy",
    "viur.security.permissions_policy",
    "viur.security.enable_coep",
    "viur.security.enable_coop",
    "viur.security.enable_corp",
    "viur.security.strict_transport_security",
    "viur.security.x_frame_options",
    "viur.security.x_xss_protection",
    "viur.security.x_content_type_options",
    "viur.security.x_permitted_cross_domain_policies",
    "viur.security.captcha.defaultCredentials",
    "viur.security.password_recovery_key_length",
    "viur.session.lifeTime",
    "viur.session.persistentFieldsOnLogin",
    "viur.session.persistentFieldsOnLogout",
    "viur.skeleton.searchPath",
    "viur.tasks.customEnvironmentHandler",
    "viur.user.roles",
    "viur.valid_application_ids",
    "viur.version",
]
"""Old config keys

Created with
    >>> from pprint import pprint
    >>> pprint(list(conf.keys()))
in viur-core==3.5.X
"""


class TestConfig(ViURTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # FIXME
        """
        cls.logger = logging.getLogger(cls.__qualname__)
        logging.basicConfig(
            format=f"%(asctime)s %(levelname)8s %(filename)s:%(lineno)03d :: %(message)s"
        )
        print(os.environ)
        cls.logger.setLevel(logging._nameToLevel[os.getenv("LOG_LEVEL", "WARNING")])
        print(cls.logger.getEffectiveLevel())
        """

    def setUp(self):
        from viur.core.config import conf
        # Same mode, unless the test-case overwrite it
        conf.strict_mode = False

    def test_old_member_access(self):
        from viur.core.config import conf

        for key in OLD_MEMBERS:
            with self.subTest(key=key):
                # FIXME self.logger.debug(f"Access conf[\"{key}\"]")
                # print(f"Access conf[\"{key}\"]")
                with self.assertWarns(DeprecationWarning):
                    _ = conf[key]

    def test_items(self):
        from viur.core.config import conf
        self.assertIsInstance(conf.items(), types.GeneratorType)
        iterator = conf.items()
        # test config is not empty (at least one item yielded)
        next(iterator)
        # test types
        for value in iterator:
            self.assertIsInstance(value, tuple)
            self.assertEqual(len(value), 2)
            self.assertIsInstance(value[0], str)

    def test_strict_mode(self):
        from viur.core.config import conf
        conf.strict_mode = True

        for key in OLD_MEMBERS:
            with (self.subTest(key=key)):
                # FIXME self.logger.debug(f"Access conf[\"{key}\"]")
                # print(f"Access conf[\"{key}\"]")
                with (
                    self.assertWarns(DeprecationWarning),
                    self.assertRaises(SyntaxError)
                ):
                    _ = conf[key]

    def test_strict_mode_setter_invalid(self):
        from viur.core.config import conf
        with self.assertRaises(TypeError):
            conf.strict_mode = "invalid-value"

    def test_backward1(self):
        from viur.core.config import conf
        _ = conf["viur.downloadUrlFor.expiration"]

    def test_backward1s(self):
        from viur.core.config import conf
        conf.strict_mode = True
        with self.assertRaises(SyntaxError) as exc:
            _ = conf["viur.downloadUrlFor.expiration"]
        msg, *_ = exc.exception.args
        self.assertIn("In strict mode,", msg)

    def test_backward2(self):
        from viur.core.config import conf
        _ = getattr(conf, "viur.downloadUrlFor.expiration")

    def test_backward2s(self):
        from viur.core.config import conf
        conf.strict_mode = True
        with self.assertRaises(AttributeError) as exc:
            _ = getattr(conf, "viur.downloadUrlFor.expiration")
        msg, *_ = exc.exception.args
        self.assertIn("(strict mode is enabled)", msg)

    def test_get1(self):
        from viur.core.config import conf
        _ = conf.get("viur.main_app")

    def test_get1s(self):
        from viur.core.config import conf
        conf.strict_mode = True
        with self.assertRaises(SyntaxError) as exc:
            _ = conf.get("viur.main_app")
        msg, *_ = exc.exception.args
        self.assertIn("In strict mode,", msg)

    def test_get2(self):
        from viur.core.config import conf
        self.assertEqual(42, conf.get("viur.notexisting", 42))

    def tearDown(self):
        from viur.core.config import conf
        conf.strict_mode = False
