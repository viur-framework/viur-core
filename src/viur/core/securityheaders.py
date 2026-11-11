"""
Deprecated module. The security-header configuration moved onto :class:`viur.core.config.Security`
(see issue #1013). Each function here now delegates to the corresponding ``conf.security.*`` method
and will be removed in a future major release. Prefer ``conf.security.<method>()`` directly.
"""

import typing as t

from deprecated.sphinx import deprecated

from viur.core.config import conf


@deprecated(version="3.10.0", reason="Use `conf.security.add_csp_rule()` instead")
def addCspRule(objectType: str, srcOrDirective: str, enforceMode: str = "monitor") -> None:
    return conf.security.add_csp_rule(objectType, srcOrDirective, enforceMode)


@deprecated(version="3.10.0", reason="Use `conf.security.extend_csp()` instead")
def extendCsp(additionalRules: dict = None, overrideRules: dict = None) -> None:
    return conf.security.extend_csp(additionalRules, overrideRules)


@deprecated(version="3.10.0", reason="Use `conf.security.set_reporting_endpoint()` instead")
def set_reporting_endpoint(name: str, url: str | None) -> None:
    return conf.security.set_reporting_endpoint(name, url)


@deprecated(version="3.10.0", reason="Use `conf.security.enable_strict_transport_security()` instead")
def enableStrictTransportSecurity(maxAge: int = 365 * 24 * 60 * 60,
                                  includeSubDomains: bool = False,
                                  preload: bool = False) -> None:
    return conf.security.enable_strict_transport_security(maxAge, includeSubDomains, preload)


@deprecated(version="3.10.0", reason="Use `conf.security.set_x_frame_options()` instead")
def setXFrameOptions(action: str, uri: t.Optional[str] = None) -> None:
    return conf.security.set_x_frame_options(action, uri)


@deprecated(version="3.10.0", reason="Use `conf.security.set_x_xss_protection()` instead")
def setXXssProtection(enable: t.Optional[bool]) -> None:
    return conf.security.set_x_xss_protection(enable)


@deprecated(version="3.10.0", reason="Use `conf.security.set_x_content_type_no_sniff()` instead")
def setXContentTypeNoSniff(enable: bool) -> None:
    return conf.security.set_x_content_type_no_sniff(enable)


@deprecated(version="3.10.0", reason="Use `conf.security.set_x_permitted_cross_domain_policies()` instead")
def setXPermittedCrossDomainPolicies(value: str) -> None:
    return conf.security.set_x_permitted_cross_domain_policies(value)


@deprecated(version="3.10.0", reason="Use `conf.security.set_referrer_policy()` instead")
def setReferrerPolicy(policy: str) -> None:
    return conf.security.set_referrer_policy(policy)


@deprecated(version="3.10.0", reason="Use `conf.security.set_permission_policy_directive()` instead")
def setPermissionPolicyDirective(directive: str, allowList: t.Optional[list[str]]) -> None:
    return conf.security.set_permission_policy_directive(directive, allowList)


@deprecated(version="3.10.0", reason="Use `conf.security.set_cross_origin_isolation()` instead")
def setCrossOriginIsolation(coep: bool, coop: str, corp: str) -> None:
    return conf.security.set_cross_origin_isolation(coep, coop, corp)


# Deprecated alias; the canonical list is Security.VALID_REFERRER_POLICIES
validReferrerPolicies = conf.security.VALID_REFERRER_POLICIES
