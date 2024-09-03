import fnmatch
from . import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
from urllib.parse import urlparse, urlunparse
import typing as t
from collections.abc import Iterable
from collections import namedtuple


class URIBone(BaseBone):
    """
       The URIBone is used for storing URI and URL.

       :param accepted_protocols: The accepted protocols can be set to allow only the provide protocols.
       :param accepted_ports The accepted ports can be set to allow only the provide ports.
       :param clean_get_params: When set to Ture the GET Parameter for the URL will be cleand.
       :param domain_allowed_list: If set only the URLs that are match with an entry of this list will be accepted.
       :param domain_disallowed_list: If set only the URLs that are not match with an entry of this list will be accepted.
       """
    type = "uri"

    def __init__(
        self,
        *,
        accepted_protocols: str | list[str] = "*",
        accepted_ports: int | str | list[int] | list[str] = "*",
        clean_get_params: bool = False,
        domain_allowed_list: list[str] | None = None,
        domain_disallowed_list: list[str] | None = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.accepted_ports = self.build_accepted_ports(accepted_ports)
        if "*" in self.accepted_ports:
            self.accepted_ports = "*"

        self.accepted_protocols = accepted_protocols
        if not isinstance(self.accepted_protocols, Iterable) or isinstance(self.accepted_protocols, str):
            self.accepted_protocols = [self.accepted_protocols]

        if "*" in accepted_protocols:
            self.accepted_protocols = "*"

        if not isinstance(clean_get_params, bool):
            raise ValueError("clean_get_params must be a boolean")

        if not isinstance(domain_allowed_list, (list, tuple)) and domain_allowed_list is not None:
            raise ValueError("domain_allowed_list must be a list or a tuple or None")

        if not isinstance(domain_disallowed_list, (list, tuple)) and domain_disallowed_list is not None:
            raise ValueError("domain_disallowed_list must be a list or a tuple or None")

        if domain_allowed_list is not None:
            if any([not isinstance(domain, str) for domain in domain_allowed_list]):
                raise ValueError("domain_allowed_list must only contain strings")

        if domain_disallowed_list is not None:
            if any([not isinstance(domain, str) for domain in domain_disallowed_list]):
                raise ValueError("domain_disallowed_list must only contain strings")

        if domain_allowed_list and domain_disallowed_list:
            raise ValueError("Only one of domain_allowed_list and domain_disallowed_list can be set")

        self.clean_get_params = clean_get_params
        self.domain_allowed_list = domain_allowed_list
        self.domain_disallowed_list = domain_disallowed_list

    def build_accepted_ports(self, accepted_ports):
        accepted_ports_value = []
        if isinstance(accepted_ports, str):
            if accepted_ports == "*":
                return "*"
            else:

                ports = accepted_ports.split(",")
                for port in ports:
                    if "-" in port:  # range of ports
                        start, end = port.split("-", 1)
                        start = int(start)
                        end = int(end)
                        if start > end:
                            raise ValueError("Start value must be less than end value")
                        accepted_ports_value.extend(range(start, end + 1))
                    else:
                        accepted_ports_value.append(int(port))
                return accepted_ports_value
        if isinstance(accepted_ports, int):
            accepted_ports_value.append(accepted_ports)
            return accepted_ports_value
        if isinstance(accepted_ports, (list, tuple)):
            for accepted_port in accepted_ports:
                accepted_ports_value.extend(self.build_accepted_ports(accepted_port))
            return accepted_ports_value
        raise ValueError("accepted_ports must be a list or a tuple or an integer or string")

    def isInvalid(self, value):
        try:
            parsed_url = urlparse(value)
        except ValueError:
            return "Can't parse URL"

        if self.accepted_ports != "*":
            if parsed_url.port not in self.accepted_ports:
                return f""""{parsed_url.port}" not in the accepted ports."""
        if self.accepted_protocols != "*":
            for protocol in self.accepted_protocols:
                if fnmatch.fnmatch(parsed_url.scheme, protocol):
                    break
            else:
                return f""""{parsed_url.scheme}" not in the accepted protocols."""
        if self.domain_allowed_list is not None:
            for domain in self.domain_allowed_list:
                if fnmatch.fnmatch(value, domain):
                    break
            else:
                return f"""Url is not in the domain allowed list."""
        if self.domain_disallowed_list is not None:
            for domain in self.domain_disallowed_list:
                if fnmatch.fnmatch(value, domain):
                    return f"""Url is in the domain disallowed list."""

    def singleValueFromClient(self, value, skel, bone_name, client_data):
        if err := self.isInvalid(value):
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]
        if self.clean_get_params:
            parsed_url = urlparse(value)
            Components = namedtuple(
                typename="Components",
                field_names=["scheme", "netloc", "path", "url", "query", "fragment"]
            )

            value = urlunparse(
                Components(
                    scheme=parsed_url.scheme,
                    netloc=parsed_url.netloc,
                    query=None,  # Set the GET-params to None to clear it
                    path=parsed_url.path,
                    url=None,
                    fragment=parsed_url.fragment,
                )
            )

        return value, None

    def structure(self) -> dict:
        return super().structure() | {
            "accepted_protocols": self.accepted_protocols,
            "accepted_ports": self.accepted_ports,
            "clean_get_params": self.clean_get_params,
            "domain_allowed_list": self.domain_allowed_list,
            "domain_disallowed_list": self.domain_disallowed_list,
        }
