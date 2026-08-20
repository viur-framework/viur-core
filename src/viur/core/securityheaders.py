"""
This module provides configuration for most of the http security headers. The features currently supported are:
    - Content security policy (https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)
    - Strict transport security (https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security)
    - X-Frame-Options (https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Frame-Options)
    - X-XSS-Protection (https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-XSS-Protection)
    - X-Content-Type-Options (https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Content-Type-Options)
    - X-Permitted-Cross-Domain-Policies (https://www.adobe.com/devnet-docs/acrobatetk/tools/AppSec/xdomain.html)
    - Referrer-Policy (https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Referrer-Policy)
    - Permissions-Policy (https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Feature-Policy)
    - Cross origin isolation (https://web.dev/coop-coep)
    - Reporting-Endpoints (https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Reporting-Endpoints)

If a feature is not yet supported, you could always set the header directly (e.g. by attaching a request
preprocessor). ViUR contains a default configuration for most of these headers where possible, however manual
review is mandatory for each project.

The content security policy will prevent inline css and javascript by default, but is configured to allow embedding
images from cloud-storage and sign-in with google.

Strict transport security is enabled by default (with a TTL of one year), but without preload or include-subdomains.

X-Frame-Options is limited to the same origin, preventing urls from this project from being embedded in iframes that
don't originate from the same origin.

X-XSS-Protection is enabled.

X-Content-Type-Options is set to nosniff

X-Permitted-Cross-Domain-Policies is set to "none", denying embedding resources in pdf files and the like

Referrer-Policy is set to strict-origin, preventing leakage of URLs to 3rd-partys.

The Permissions-Policy will only allow auto-play by default (thus access to the camera-api etc. is disabled)

Cross origin isolation is currently disabled by default (as it's incompatible with many popular services like
embedding a map or sign-in with google).

No reporting endpoints are configured by default; see :func:`set_reporting_endpoint` on how to receive reports.

ViUR also protects it's cookies by default (setting httponly, secure and samesite=lax). This can be changed by
setting the corresponding class-level variables on class:`Session<viur.core.session.Session>`.
"""

from viur.core.config import conf
from viur.core import current
import logging
import re
import typing as t

# Endpoint names are structured-field keys, see https://www.rfc-editor.org/rfc/rfc8941#section-3.1.2
_REPORTING_ENDPOINT_NAME_RE = re.compile(r"^[a-z*][a-z0-9_.*-]*$")


def addCspRule(objectType: str, srcOrDirective: str, enforceMode: str = "monitor"):
    """
        This function helps configuring and reporting of content security policy rules and violations.
        To enable CSP, call addCspRule() from your projects main file before calling server.setup().

        ..  code-block:: python

            # Example Usage

            # Enable CSP for all types and made us the only allowed source
            security.addCspRule("default-src","self","enforce")

            # Start a new set of rules for stylesheets whitelist us
            security.addCspRule("style-src","self","enforce")

            # This is currently needed for TextBones!
            security.addCspRule("style-src","unsafe-inline","enforce")

        If you don't want these rules to be enforced and just getting a report of violations replace "enforce" with
        "monitor". To have violations reported, name an endpoint configured via :meth:`set_reporting_endpoint`::

            security.set_reporting_endpoint("csp", "/cspReport")
            security.addCspRule("report-to", "csp", "enforce")

        and register a function at /cspReport to handle the reports. As ``report-to`` is not supported by every
        browser yet, the deprecated ``report-uri`` directive can be added as a fallback; browsers understanding
        both will ignore it::

            security.addCspRule("report-uri", "/cspReport", "enforce")

        ..note::

            Our tests showed that enabling a report-url on production systems has limited use. There are literally
            thousands of browser-extensions out there that inject code into the pages displayed. This causes a whole
            flood of violations-spam to your report-url.


        :param objectType: For which type of objects should this directive be enforced? (script-src, img-src, ...)
        :param srcOrDirective: Either a domain which should be white-listed or a CSP-Keyword like 'self', 'unsafe-inline', etc.
        :param enforceMode: Should this directive be enforced or just logged?
    """
    assert enforceMode in ["monitor", "enforce"], "enforceMode must be 'monitor' or 'enforce'!"
    assert objectType in {
        # Fetch directives
        "default-src", "child-src", "connect-src", "fenced-frame-src", "font-src", "frame-src", "img-src",
        "manifest-src", "media-src", "object-src", "prefetch-src", "script-src", "script-src-elem",
        "script-src-attr", "style-src", "style-src-elem", "style-src-attr", "worker-src",
        # Document directives
        "base-uri", "sandbox",
        # Navigation directives
        "form-action", "frame-ancestors",
        # Reporting directives
        "report-uri", "report-to",
        # Other directives
        "require-trusted-types-for", "trusted-types", "upgrade-insecure-requests", "block-all-mixed-content",
    }
    assert conf.main_app is None, "You cannot modify CSP rules after server.buildApp() has been run!"
    assert not any(
        [x in srcOrDirective for x in [";", "'", "\"", "\n", ","]]), "Invalid character in srcOrDirective!"
    if conf.security.content_security_policy is None:
        conf.security.content_security_policy = {"_headerCache": {}}
    if enforceMode not in conf.security.content_security_policy:
        conf.security.content_security_policy[enforceMode] = {}
    if objectType in ("report-uri", "report-to"):
        # Both directives take exactly one value; a second one would be ignored by the browser anyway
        conf.security.content_security_policy[enforceMode][objectType] = [srcOrDirective]
    else:
        if objectType not in conf.security.content_security_policy[enforceMode]:
            conf.security.content_security_policy[enforceMode][objectType] = []
        if srcOrDirective not in conf.security.content_security_policy[enforceMode][objectType]:
            conf.security.content_security_policy[enforceMode][objectType].append(srcOrDirective)


def _rebuildCspHeaderCache():
    """
        Rebuilds the internal conf.security.content_security_policy["_headerCache"] dictionary, ie. it constructs
        the Content-Security-Policy-Report-Only and Content-Security-Policy headers based on what has been passed
        to 'addRule' earlier on. Should not be called directly.
    """
    conf.security.content_security_policy["_headerCache"] = {}
    for enforceMode in ["monitor", "enforce"]:
        resStr = ""
        if enforceMode not in conf.security.content_security_policy:
            continue
        for key, values in conf.security.content_security_policy[enforceMode].items():
            resStr += key
            for value in values:
                resStr += " "
                if value in {"self", "unsafe-inline", "unsafe-eval", "script", "none"} or \
                    any([value.startswith(x) for x in ["sha256-", "sha384-", "sha512-"]]):
                    # We don't permit nonce- in project wide config as this will be reused on multiple requests
                    resStr += f"'{value}'"
                else:
                    resStr += value
            resStr += "; "
        if enforceMode == "monitor":
            conf.security.content_security_policy["_headerCache"][
                "Content-Security-Policy-Report-Only"] = resStr
        else:
            conf.security.content_security_policy["_headerCache"]["Content-Security-Policy"] = resStr


def extendCsp(additionalRules: dict = None, overrideRules: dict = None) -> None:
    """
        Adds additional csp rules to the current request. ViUR will emit a default csp-header based on the
        project-wide config. For some requests, it's needed to extend or override these rules without having to include
        them in the project config. Each dictionary must be in the same format as the
        conf.security.content_security_policy. Values in additionalRules will extend the project-specific
        configuration, while overrideRules will replace them.

        ..Note: This function will only work on CSP-Rules in "enforce" mode, "monitor" is not suppored

        :param additionalRules: Dictionary with additional csp-rules to emit
        :param overrideRules: Values in this dictionary will override the corresponding default rule
    """
    assert additionalRules or overrideRules, "Either additionalRules or overrideRules must be given!"
    tmpDict = {}  # Copy the project-wide config in
    if conf.security.content_security_policy.get("enforce"):
        tmpDict.update({k: v[:] for k, v in conf.security.content_security_policy["enforce"].items()})
    if overrideRules:  # Merge overrideRules
        for k, v in overrideRules.items():
            if v is None and k in tmpDict:
                del tmpDict[k]
            else:
                tmpDict[k] = v
    if additionalRules:  # Merge the extension dict
        for k, v in additionalRules.items():
            if k not in tmpDict:
                tmpDict[k] = []
            tmpDict[k].extend(v)
    resStr = ""  # Rebuild the CSP-Header
    for key, values in tmpDict.items():
        resStr += key
        for value in values:
            resStr += " "
            if value in {"self", "unsafe-inline", "unsafe-eval", "script", "none"} or \
                any([value.startswith(x) for x in ["nonce-", "sha256-", "sha384-", "sha512-"]]):
                resStr += f"'{value}'"
            else:
                resStr += value
        resStr += "; "
    current.request.get().response.headers["Content-Security-Policy"] = resStr


def set_reporting_endpoint(name: str, url: str | None) -> None:
    """Configure a named endpoint reports are being sent to.

    All endpoints configured this way are emitted as ``Reporting-Endpoints`` http-header with each request.
    Other headers reference an endpoint by its name, i.e. the CSP-directive ``report-to``:

    ..  code-block:: python

        # Example Usage

        security.set_reporting_endpoint("csp", "/cspReport")
        security.addCspRule("report-to", "csp", "enforce")

    The name ``default`` is special: the browser uses it for reports whose header cannot name an endpoint
    on its own, as well as for reports not caused by a header at all (i.e. deprecation reports).

    The endpoint receives a POST with the content-type ``application/reports+json``, carrying a *list* of
    reports rather than a single one: browsers queue them up and deliver a batch a few seconds later. The
    deprecated ``report-uri`` directive behaves differently, it posts one ``application/csp-report`` per
    violation right away. Reports of a violation also name the precise directive (``style-src-elem``),
    where the legacy format falls back to the broader one (``style-src``).

    .. note::

        Reports are only sent from a https origin, and only to a https endpoint. A relative url inherits
        the scheme of the document, so a development server on plain http receives nothing -- not even
        when the endpoint is given as an absolute https url. Putting a TLS proxy in front of the
        development server is enough to make reporting work locally.

    .. note::

        Browsers supporting ``report-to`` ignore ``report-uri`` once both directives are present. Keeping
        the deprecated one around therefore only serves browsers without Reporting-API support; it is no
        way around the https requirement.

    .. note::

        Our tests showed that enabling reporting on production systems has limited use. There are literally
        thousands of browser-extensions out there that inject code into the pages displayed. This causes a
        whole flood of violations-spam to your endpoint.

    :param name: The name other headers use to reference this endpoint.
    :param url: The url the reports are sent to. Pass None to remove a previously configured endpoint.
    :raises ValueError: If either name or url is unsuitable.
    """
    if url is None:
        conf.security.reporting_endpoints.pop(name, None)
        return
    _validate_reporting_endpoint(name, url)
    conf.security.reporting_endpoints[name] = url


def _build_reporting_endpoints_header() -> str:
    """Build the value of the ``Reporting-Endpoints`` header.

    Uses what has been passed to :func:`set_reporting_endpoint` earlier on. An empty string is returned if no
    endpoint is configured, in which case the header must be omitted. Should not be called directly.
    """
    return ", ".join(f'{name}="{url}"' for name, url in conf.security.reporting_endpoints.items())


def _validate_reporting_config() -> None:
    """Ensure the reporting configuration as a whole is sane.

    Every configured endpoint must be emittable and each CSP ``report-to`` directive must name one of them.
    Called on startup, should not be called directly.

    :raises ValueError: If a configured endpoint is unsuitable.
    """
    for name, url in conf.security.reporting_endpoints.items():
        _validate_reporting_endpoint(name, url)
    for enforce_mode in ("monitor", "enforce"):
        for name in (conf.security.content_security_policy or {}).get(enforce_mode, {}).get("report-to", []):
            if name not in conf.security.reporting_endpoints:
                logging.warning(f"The CSP directive report-to names the endpoint {name!r} in {enforce_mode!r} mode, "
                                f"but no such reporting endpoint is configured. The browser will drop the reports.")
    if conf.security.reporting_endpoints and conf.instance.is_dev_server:
        logging.warning("Reporting endpoints are configured, but browsers drop them unless they are served over "
                        "https -- expect no reports on a plain http development server.")


def _validate_reporting_endpoint(name: str, url: str) -> None:
    """Ensure a reporting endpoint can be emitted as ``Reporting-Endpoints`` header without breaking it.

    :raises ValueError: If either name or url is unsuitable.
    """
    if not _REPORTING_ENDPOINT_NAME_RE.match(name):
        raise ValueError(f"Invalid endpoint name {name!r}, must match {_REPORTING_ENDPOINT_NAME_RE.pattern}")
    if not url or any(char in url for char in "\"',;\\") or any(char.isspace() for char in url):
        raise ValueError(f"Invalid character in url {url!r} of endpoint {name!r}")
    if "://" in url and not url.lower().startswith("https://"):
        raise ValueError(f"An absolute url must use the https scheme, got {url!r} for endpoint {name!r}")


def enableStrictTransportSecurity(maxAge: int = 365 * 24 * 60 * 60,
                                  includeSubDomains: bool = False,
                                  preload: bool = False) -> None:
    """
        Enables HTTP strict transport security.

        :param maxAge: The time, in seconds, that the browser should remember that this site is only to be accessed using HTTPS.
        :param includeSubDomains: If this parameter is set, this rule applies to all of the site's subdomains as well.
        :param preload: If set, we'll issue a hint that preloading would be appreciated.
    """
    conf.security.strict_transport_security = f"max-age={maxAge}"
    if includeSubDomains:
        conf.security.strict_transport_security += "; includeSubDomains"
    if preload:
        conf.security.strict_transport_security += "; preload"


def setXFrameOptions(action: str, uri: t.Optional[str] = None) -> None:
    """
        Sets X-Frame-Options to prevent click-jacking attacks.
        :param action: off | deny | sameorigin | allow-from
        :param uri: URL to whitelist
    """
    if action == "off":
        conf.security.x_frame_options = None
    elif action in ["deny", "sameorigin"]:
        conf.security.x_frame_options = (action, None)
    elif action == "allow-from":
        if uri is None or not (uri.lower().startswith("https://") or uri.lower().startswith("http://")):
            raise ValueError("If action is allow-from, an uri MUST be given and start with http(s)://")
        conf.security.x_frame_options = (action, uri)


def setXXssProtection(enable: t.Optional[bool]) -> None:
    """
        Sets X-XSS-Protection header. If set, mode will always be block.
        :param enable: Enable the protection or not. Set to None to drop this header
    """
    if enable is True or enable is False or enable is None:
        conf.security.x_xss_protection = enable
    else:
        raise ValueError("enable must be exactly one of None | True | False")


def setXContentTypeNoSniff(enable: bool) -> None:
    """
        Sets X-Content-Type-Options if enable is true, otherwise no header is emited.
        :param enable: Enable emitting this header or not
    """
    if enable is True or enable is False:
        conf.security.x_content_type_options = enable
    else:
        raise ValueError("enable must be one of True | False")


def setXPermittedCrossDomainPolicies(value: str) -> None:
    if value not in [None, "none", "master-only", "by-content-type", "all"]:
        raise ValueError("value [None, \"none\", \"master-only\", \"by-content-type\", \"all\"]")
    conf.security.x_permitted_cross_domain_policies = value


# Valid values for the referrer-header as per https://www.w3.org/TR/referrer-policy/#referrer-policies
validReferrerPolicies = [
    "no-referrer",
    "no-referrer-when-downgrade",
    "origin",
    "origin-when-cross-origin",
    "same-origin",
    "strict-origin",
    "strict-origin-when-cross-origin",
    "unsafe-url"
]


def setReferrerPolicy(policy: str):  # fixme: replace str with literal[validreferrerpolicies] when py3.8 gets supported - This is not how Literal works... We can use a Enum for this.
    """
        :param policy: The referrer policy to send
    """
    assert policy in validReferrerPolicies, f"Policy must be one of {validReferrerPolicies}"
    conf.security.referrer_policy = policy


def _rebuildPermissionHeaderCache() -> None:
    """
        Rebuilds the internal conf.security.permissions_policy["_headerCache"] string, ie. it constructs
        the actual header string that's being emitted to the clients.
    """
    conf.security.permissions_policy["_headerCache"] = ", ".join([
        "%s=(%s)" % (k, " ".join([("\"%s\"" % x if x != "self" else x) for x in v]))
        for k, v in conf.security.permissions_policy.items() if k != "_headerCache"
    ])


def setPermissionPolicyDirective(directive: str, allowList: t.Optional[list[str]]) -> None:
    """
        Set the permission policy.
            :param directive: The directive to set.
                Must be one of https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Feature-Policy#directives
            :param allowList:
                The list of allowed origins. Use "self" to allow the current domain.
                Empty list means the feature will be disabled by the browser (it's not accessible by javascript)
    """
    conf.security.permissions_policy[directive] = allowList


def setCrossOriginIsolation(coep: bool, coop: str, corp: str) -> None:
    """
        Configures the cross origin isolation header that ViUR may emit. This is necessary to enable features like
        SharedArrayBuffer. See https://web.dev/coop-coep for more information.

            :param coep: If set True, we'll emit Cross-Origin-Embedder-Policy:
                - require-corp
            :param coop: The value for the Cross-Origin-Opener-Policy header. Valid values are
                - same-origin
                - same-origin-allow-popups
                - unsafe-none
            :param corp: The value for the Cross-Origin-Resource-Policy header. Valid values are
                - same-site
                - same-origin
                - cross-origin
    """
    assert coop in ["same-origin", "same-origin-allow-popups", "unsafe-none"], "Invalid value for the COOP Header"
    assert corp in ["same-site", "same-origin", "cross-origin"], "Invalid value for the CORP Header"
    conf.security.enable_coep = bool(coep)
    conf.security.enable_coop = coop
    conf.security.enable_corp = corp
