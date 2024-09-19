#!/usr/bin/env python3
"""
Replace the old conf["dict-key"] syntax with the new conf.attribute syntax,
which was introduced in #833.
"""

import argparse
import difflib
from pathlib import Path

mapping = {
    "admin.color.primary": "admin.color_primary",
    "admin.color.secondary": "admin.color_secondary",
    "admin.login.background": "admin.login_background",
    "admin.login.logo": "admin.login_logo",
    "admin.logo": "admin.logo",
    "admin.moduleGroups": "admin.module_groups",
    "admin.name": "admin.name",
    "admin.scriptor": "admin.scriptor",
    "viur.accessRights": "user.access_rights",
    "viur.availableLanguages": "i18n.available_languages",
    "viur.bone.boolean.str2true": "bone_boolean_str2true",
    "viur.cacheEnvironmentKey": "cache_environment_key",
    "viur.compatibility": "compatibility",
    "viur.db.engine": "db_engine",
    "viur.debug.skeleton.fromClient": "debug.skeleton.fromClient",
    "viur.debug.trace": "debug.trace",
    "viur.debug.traceExceptions": "debug.trace_exceptions",
    "viur.debug.traceExternalCallRouting": "debug.trace_external_call_routing",
    "viur.debug.traceInternalCallRouting": "debug.trace_internal_call_routing",
    "viur.defaultLanguage": "i18n.default_language",
    "viur.dev_server_cloud_logging": "debug.dev_server_cloud_logging",
    "viur.disableCache": "debug.disable_cache",
    "viur.domainLanguageMapping": "i18n.domain_language_mapping",
    "viur.email.admin_recipients": "email.admin_recipients",
    "viur.email.logRetention": "email.log_retention",
    "viur.email.recipientOverride": "email.recipient_override",
    "viur.email.senderOverride": "email.sender_override",
    "viur.email.sendFromLocalDevelopmentServer": "email.send_from_local_development_server",
    "viur.email.transportClass": "email.transport_class",
    "viur.email.mailjet_api_key": "email.mailjet_api_key",
    "viur.email.mailjet_api_secret": "email.mailjet_api_secret",
    "viur.email.sendInBlue.apiKey": "email.sendinblue_api_key",
    "viur.errorHandler": "error_handler",
    "viur.file.derivers": "file_derivations",
    "viur.file.hmacKey": "file_hmac_key",
    "viur.forceSSL": "security.force_ssl",
    "viur.instance.app_version": "instance.app_version",
    "viur.instance.core_base_path": "instance.core_base_path",
    "viur.instance.is_dev_server": "instance.is_dev_server",
    "viur.instance.project_base_path": "instance.project_base_path",
    "viur.instance.project_id": "instance.project_id",
    "viur.instance.version_hash": "instance.version_hash",
    "viur.languageAliasMap": "i18n.language_alias_map",
    "viur.languageMethod": "i18n.language_method",
    "viur.languageModuleMap": "i18n.language_module_map",
    "viur.mainApp": "main_app",
    "viur.mainResolver": "main_resolver",
    "viur.maxPasswordLength": "user.max_password_length",
    "viur.maxPostParamsCount": "max_post_params_count",
    "viur.moduleconf.admin_info": "moduleconf_admin_info",
    "viur.noSSLCheckUrls": "security.no_ssl_check_urls",
    "viur.otp.issuer": "user.otp_issuer",
    "viur.render.html.downloadUrlExpiration": "render_html_download_url_expiration",
    "viur.render.json.downloadUrlExpiration": "render_json_download_url_expiration",
    "viur.requestPreprocessor": "request_preprocessor",
    "viur.script.admin_info": "script_admin_info",
    "viur.search_valid_chars": "search_valid_chars",
    "viur.security.captcha.defaultCredentials": "security.captcha.defaultCredentials",
    "viur.security.contentSecurityPolicy": "security.contentSecurityPolicy",
    "viur.security.enableCOEP": "security.enable_coep",
    "viur.security.enableCOOP": "security.enable_coop",
    "viur.security.enableCORP": "security.enable_corp",
    "viur.security.password_recovery_key_length": "security.password_recovery_key_length",
    "viur.security.permissionsPolicy": "security.permissions_policy",
    "viur.security.referrerPolicy": "security.referrer_policy",
    "viur.security.strictTransportSecurity": "security.strict_transport_security",
    "viur.security.xContentTypeOptions": "security.x_content_type_options",
    "viur.security.xFrameOptions": "security.x_frame_options",
    "viur.security.xPermittedCrossDomainPolicies": "security.x_permitted_cross_domain_policies",
    "viur.security.xXssProtection": "security.x_xss_protection",
    "viur.session.lifeTime": "user.session_life_time",
    "viur.session.persistentFieldsOnLogin": "user.session_persistent_fields_on_login",
    "viur.session.persistentFieldsOnLogout": "user.session_persistent_fields_on_logout",
    "viur.skeleton.searchPath": "skeleton_search_path",
    "viur.static.embedSvg.path": "static_embed_svg_path",
    "viur.tasks.customEnvironmentHandler": "tasks_custom_environment_handler",
    "viur.user.roles": "user.roles",
    "viur.validApplicationIDs": "valid_application_ids",
    "viur.version": "version",
}

# Build up the replaceable expressions
lookup = {}
for old_key, new_attr in mapping.items():
    for quoting in ("'", "\""):
        old_expr = f"conf[{quoting}{old_key}{quoting}]"
        lookup[old_expr] = f"conf.{new_attr}"


def replace_in_file(args: argparse.Namespace, file: Path):
    """
    Performs the conversion on a file with the provided options.
    """
    original_content = content = file.read_text()

    count = 0
    for old_expr, new_expr in lookup.items():
        if old_expr in content:
            content = content.replace(old_expr, new_expr)
            count += 1

    if count:
        if not args.dryrun:
            if not args.daredevil:
                file.replace(f"{file}.bak")
            file.write_text(content)
            print(f"Modified {file}: {count} replacement(s)")

        else:
            print(
                "\n".join(
                    difflib.unified_diff(
                        original_content.splitlines(),
                        content.splitlines(),
                        f"Current {file.relative_to(args.path)}",
                        f"New {file.relative_to(args.path)}",
                    )
                )
            )


def main():
    # Get arguments
    ap = argparse.ArgumentParser(
        description="ViUR-core migrate config 3.5 --> 3.6"
    )

    ap.add_argument(
        "path",
        type=str,
        help="Path to file or folder",
    )

    ap.add_argument(
        "--ignore",
        type=str,
        nargs="*",
        help="Ignore these paths (must be relative to the root path)",
    )

    ap.add_argument(
        "-d", "--dryrun",
        action="store_true",
        help="Dry-run for testing, don't modify files"
    )
    ap.add_argument(
        "-x", "--daredevil",
        action="store_true",
        help="Don't make backups of files, just replace and deal with it"
    )

    args = ap.parse_args()

    path = Path(args.path)
    if path.is_file():
        return replace_in_file(args, path)
    elif not path.is_dir():
        raise IOError(f"The path {args.path!r} is invalid (neither a file or dir)!")

    ignore_paths = [path.joinpath(_path)
                    for _path in args.ignore or []]

    for file in path.rglob("**/*.py"):
        for ignore in ignore_paths:
            if file.is_relative_to(ignore):
                # file is inside a ignored path
                print(f"Ignoring {file}")
                break
        else:
            replace_in_file(args, file)


if __name__ == "__main__":
    main()
