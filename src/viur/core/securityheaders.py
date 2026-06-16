"""
Deprecated module. The security-header configuration moved onto :class:`viur.core.config.Security`
(see issue #1013). Each function here now delegates to the corresponding ``conf.security.*`` method
and will be removed in a future major release. Prefer ``conf.security.<method>()`` directly.
"""

import logging
import typing as t
import warnings

from viur.core.config import conf


def _deprecated(old: str, new: str) -> None:
    msg = f"`securityheaders.{old}` is deprecated; use `conf.security.{new}` instead!"
    warnings.warn(msg, DeprecationWarning, stacklevel=3)
    logging.warning(msg)


def addCspRule(objectType: str, srcOrDirective: str, enforceMode: str = "monitor") -> None:
    _deprecated("addCspRule", "add_csp_rule")
    return conf.security.add_csp_rule(objectType, srcOrDirective, enforceMode)


def extendCsp(additionalRules: dict = None, overrideRules: dict = None) -> None:
    _deprecated("extendCsp", "extend_csp")
    return conf.security.extend_csp(additionalRules, overrideRules)


def enableStrictTransportSecurity(maxAge: int = 365 * 24 * 60 * 60,
                                  includeSubDomains: bool = False,
                                  preload: bool = False) -> None:
    _deprecated("enableStrictTransportSecurity", "enable_strict_transport_security")
    return conf.security.enable_strict_transport_security(maxAge, includeSubDomains, preload)


def setXFrameOptions(action: str, uri: t.Optional[str] = None) -> None:
    _deprecated("setXFrameOptions", "set_x_frame_options")
    return conf.security.set_x_frame_options(action, uri)


def setXXssProtection(enable: t.Optional[bool]) -> None:
    _deprecated("setXXssProtection", "set_x_xss_protection")
    return conf.security.set_x_xss_protection(enable)


def setXContentTypeNoSniff(enable: bool) -> None:
    _deprecated("setXContentTypeNoSniff", "set_x_content_type_no_sniff")
    return conf.security.set_x_content_type_no_sniff(enable)


def setXPermittedCrossDomainPolicies(value: str) -> None:
    _deprecated("setXPermittedCrossDomainPolicies", "set_x_permitted_cross_domain_policies")
    return conf.security.set_x_permitted_cross_domain_policies(value)


def setReferrerPolicy(policy: str) -> None:
    _deprecated("setReferrerPolicy", "set_referrer_policy")
    return conf.security.set_referrer_policy(policy)


def setPermissionPolicyDirective(directive: str, allowList: t.Optional[list[str]]) -> None:
    _deprecated("setPermissionPolicyDirective", "set_permission_policy_directive")
    return conf.security.set_permission_policy_directive(directive, allowList)


def setCrossOriginIsolation(coep: bool, coop: str, corp: str) -> None:
    _deprecated("setCrossOriginIsolation", "set_cross_origin_isolation")
    return conf.security.set_cross_origin_isolation(coep, coop, corp)


# Deprecated alias; the canonical list is Security.VALID_REFERRER_POLICIES
validReferrerPolicies = conf.security.VALID_REFERRER_POLICIES
