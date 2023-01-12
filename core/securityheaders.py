"""
    This module provides configuration for most of the http security headers.
    The features currently supported are
        - Content security policy (https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)
        - Strict transport security (https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security)
        - X-Frame-Options (https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Frame-Options)
        - X-XSS-Protection (https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-XSS-Protection)
        - X-Content-Type-Options (https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Content-Type-Options)
        - X-Permitted-Cross-Domain-Policies (https://www.adobe.com/devnet-docs/acrobatetk/tools/AppSec/xdomain.html)
        - Referrer-Policy (https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Referrer-Policy)
        - Permissions-Policy (https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Feature-Policy)
        - Cross origin isolation (https://web.dev/coop-coep)

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


    ViUR also protects it's cookies by default (setting httponly, secure and samesite=lax). This can be changed by
    setting the corresponding class-level variables on class:`GaeSession<viur.core.session.GaeSession>`.
"""

from viur.core.config import conf
from viur.core.utils import currentRequest
import logging
from typing import Literal, Optional, List


def addCspRule(objectType: str, srcOrDirective: str, enforceMode: str = "monitor"):
    """
        This function helps configuring and reporting of content security policy rules and violations.
        To enable CSP, call addCspRule() from your projects main file before calling server.setup().

        Example usage::

            security.addCspRule("default-src","self","enforce") #Enable CSP for all types and made us the only allowed source

            security.addCspRule("style-src","self","enforce") # Start a new set of rules for stylesheets whitelist us
            security.addCspRule("style-src","unsafe-inline","enforce") # This is currently needed for TextBones!

        If you don't want these rules to be enforced and just getting a report of violations replace "enforce" with
        "monitor". To add a report-url use something like::

            security.addCspRule("report-uri","/cspReport","enforce")

        and register a function at /cspReport to handle the reports.

        ..note::

            Our tests showed that enabling a report-url on production systems has limited use. There are literally
            thousands of browser-extensions out there that inject code into the pages displayed. This causes a whole
            flood of violations-spam to your report-url.


        :param objectType: For which type of objects should this directive be enforced? (script-src, img-src, ...)
        :param srcOrDirective: Either a domain which should be white-listed or a CSP-Keyword like 'self', 'unsafe-inline', etc.
        :param enforceMode: Should this directive be enforced or just logged?
    """
    assert enforceMode in ["monitor", "enforce"], "enforceMode must be 'monitor' or 'enforce'!"
    assert objectType in {"default-src", "script-src", "object-src", "style-src", "img-src", "media-src",
                          "frame-src", "font-src", "connect-src", "report-uri", "frame-ancestors", "child-src",
                          "form-action", "require-trusted-types-for"}
    assert conf["viur.mainApp"] is None, "You cannot modify CSP rules after server.buildApp() has been run!"
    assert not any(
        [x in srcOrDirective for x in [";", "'", "\"", "\n", ","]]), "Invalid character in srcOrDirective!"
    if conf["viur.security.contentSecurityPolicy"] is None:
        conf["viur.security.contentSecurityPolicy"] = {"_headerCache": {}}
    if not enforceMode in conf["viur.security.contentSecurityPolicy"]:
        conf["viur.security.contentSecurityPolicy"][enforceMode] = {}
    if objectType == "report-uri":
        conf["viur.security.contentSecurityPolicy"][enforceMode]["report-uri"] = [srcOrDirective]
    else:
        if not objectType in conf["viur.security.contentSecurityPolicy"][enforceMode]:
            conf["viur.security.contentSecurityPolicy"][enforceMode][objectType] = []
        if not srcOrDirective in conf["viur.security.contentSecurityPolicy"][enforceMode][objectType]:
            conf["viur.security.contentSecurityPolicy"][enforceMode][objectType].append(srcOrDirective)


def _rebuildCspHeaderCache():
    """
        Rebuilds the internal conf["viur.security.contentSecurityPolicy"]["_headerCache"] dictionary, ie. it constructs
        the Content-Security-Policy-Report-Only and Content-Security-Policy headers based on what has been passed
        to 'addRule' earlier on. Should not be called directly.
    """
    conf["viur.security.contentSecurityPolicy"]["_headerCache"] = {}
    for enforceMode in ["monitor", "enforce"]:
        resStr = ""
        if not enforceMode in conf["viur.security.contentSecurityPolicy"]:
            continue
        for key, values in conf["viur.security.contentSecurityPolicy"][enforceMode].items():
            resStr += key
            for value in values:
                resStr += " "
                if value in {"self", "unsafe-inline", "unsafe-eval", "script", "none"} or \
                    any([value.startswith(x) for x in ["sha256-", "sha384-", "sha512-"]]):
                    # We don't permit nonce- in project wide config as this will be reused on multiple requests
                    resStr += "'%s'" % value
                else:
                    resStr += value
            resStr += "; "
        if enforceMode == "monitor":
            conf["viur.security.contentSecurityPolicy"]["_headerCache"][
                "Content-Security-Policy-Report-Only"] = resStr
        else:
            conf["viur.security.contentSecurityPolicy"]["_headerCache"]["Content-Security-Policy"] = resStr


def extendCsp(additionalRules: dict = None, overrideRules: dict = None) -> None:
    """
        Adds additional csp rules to the current request. ViUR will emit a default csp-header based on the
        project-wide config. For some requests, it's needed to extend or override these rules without having to include
        them in the project config. Each dictionary must be in the same format as the
        conf["viur.security.contentSecurityPolicy"]. Values in additionalRules will extend the project-specific
        configuration, while overrideRules will replace them.

        ..Note: This function will only work on CSP-Rules in "enforce" mode, "monitor" is not suppored

        :param additionalRules: Dictionary with additional csp-rules to emit
        :param overrideRules: Values in this dictionary will override the corresponding default rule
    """
    assert additionalRules or overrideRules, "Either additionalRules or overrideRules must be given!"
    tmpDict = {}  # Copy the project-wide config in
    if conf["viur.security.contentSecurityPolicy"].get("enforce"):
        tmpDict.update({k: v[:] for k, v in conf["viur.security.contentSecurityPolicy"]["enforce"].items()})
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
                resStr += "'%s'" % value
            else:
                resStr += value
        resStr += "; "
    currentRequest.get().response.headers["Content-Security-Policy"] = resStr


def enableStrictTransportSecurity(maxAge: int = 365 * 24 * 60 * 60,
                                  includeSubDomains: bool = False,
                                  preload: bool = False) -> None:
    """
        Enables HTTP strict transport security.

        :param maxAge: The time, in seconds, that the browser should remember that this site is only to be accessed using HTTPS.
        :param includeSubDomains: If this parameter is set, this rule applies to all of the site's subdomains as well.
        :param preload: If set, we'll issue a hint that preloading would be appreciated.
    """
    conf["viur.security.strictTransportSecurity"] = "max-age=%s" % maxAge
    if includeSubDomains:
        conf["viur.security.strictTransportSecurity"] += "; includeSubDomains"
    if preload:
        conf["viur.security.strictTransportSecurity"] += "; preload"


def setXFrameOptions(action: str, uri: Optional[str] = None) -> None:
    """
        Sets X-Frame-Options to prevent click-jacking attacks.
        :param action: off | deny | sameorigin | allow-from
        :param uri: URL to whitelist
    """
    if action == "off":
        conf["viur.security.xFrameOptions"] = None
    elif action in ["deny", "sameorigin"]:
        conf["viur.security.xFrameOptions"] = (action, None)
    elif action == "allow-from":
        if uri is None or not (uri.lower().startswith("https://") or uri.lower().startswith("http://")):
            raise ValueError("If action is allow-from, an uri MUST be given and start with http(s)://")
        conf["viur.security.xFrameOptions"] = (action, uri)


def setXXssProtection(enable: Optional[bool]) -> None:
    """
        Sets X-XSS-Protection header. If set, mode will always be block.
        :param enable: Enable the protection or not. Set to None to drop this header
    """
    if enable is True or enable is False or enable is None:
        conf["viur.security.xXssProtection"] = enable
    else:
        raise ValueError("enable must be exactly one of None | True | False")


def setXContentTypeNoSniff(enable: bool) -> None:
    """
        Sets X-Content-Type-Options if enable is true, otherwise no header is emited.
        :param enable: Enable emitting this header or not
    """
    if enable is True or enable is False:
        conf["viur.security.xContentTypeOptions"] = enable
    else:
        raise ValueError("enable must be one of True | False")


def setXPermittedCrossDomainPolicies(value: str) -> None:
    if value not in [None, "none", "master-only", "by-content-type", "all"]:
        raise ValueError("value [None, \"none\", \"master-only\", \"by-content-type\", \"all\"]")
    conf["viur.security.xPermittedCrossDomainPolicies"] = value


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
    assert policy in validReferrerPolicies, "Policy must be one of %s" % validReferrerPolicies
    conf["viur.security.referrerPolicy"] = policy


def _rebuildPermissionHeaderCache() -> None:
    """
        Rebuilds the internal conf["viur.security.permissionsPolicy"]["_headerCache"] string, ie. it constructs
        the actual header string that's being emitted to the clients.
    """
    conf["viur.security.permissionsPolicy"]["_headerCache"] = ", ".join([
        "%s=(%s)" % (k, " ".join([("\"%s\"" % x if x != "self" else x) for x in v]))
        for k, v in conf["viur.security.permissionsPolicy"].items() if k != "_headerCache"
    ])


def setPermissionPolicyDirective(directive: str, allowList: Optional[List[str]]) -> None:
    """
        Set the permission policy :param: directive the list of allowed origins in :param: allowList.
        :param directive: The directive to set. Must be one of
            https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Feature-Policy#directives
        :param allowList: The list of allowed origins. Use "self" to allow the current domain. Empty list means the feature
            will be disabled by the browser (it's not accessible by javascript)
    """
    conf["viur.security.permissionsPolicy"][directive] = allowList


def setCrossOriginIsolation(coep: bool, coop: str, corp: str) -> None:
    """
        Configures the cross origin isolation header that ViUR may emit. This is necessary to enable features like
        SharedArrayBuffer. See https://web.dev/coop-coep for more information.
        :param coep: If set True, we'll emit Cross-Origin-Embedder-Policy: require-corp
        :param coop: The value for the Cross-Origin-Opener-Policy header. Valid values are
            same-origin | same-origin-allow-popups | unsafe-none
        :param corp: The value for the Cross-Origin-Resource-Policy header. Valid values are
            same-site | same-origin | cross-origin
    """
    assert coop in ["same-origin", "same-origin-allow-popups", "unsafe-none"], "Invalid value for the COOP Header"
    assert corp in ["same-site", "same-origin", "cross-origin"], "Invalid value for the CORP Header"
    conf["viur.security.enableCOEP"] = bool(coep)
    conf["viur.security.enableCOOP"] = coop
    conf["viur.security.enableCORP"] = corp
