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
       ..  code-block:: python
            # Example
            URIBone(accepted_ports=1)
            URIBone(accepted_ports="2")
            URIBone(accepted_ports="1-4")
            URIBone(accepted_ports=[1,"2","4-10"])
       :param clean_get_params: When set to Ture the GET Parameter for the URL will be cleand.
       :param domain_allowed_list: If set only the URLs that are match with an entry of this list will be accepted.
       :param domain_disallowed_list: If set only the URLs that are not match
            with an entry of this list will be accepted.
       :param local_allowed_list: If True the URLs that are local paths will be prefixed with "/".
       """
    type = "uri"

    def __init__(
        self,
        *,
        accepted_protocols: str | t.Iterable[str] | None = None,
        accepted_ports: int | str | t.Iterable[int] | t.Iterable[str] | None = None,
        clean_get_params: bool = False,
        domain_allowed_list: t.Iterable[str] | None = None,
        domain_disallowed_list: t.Iterable[str] | None = None,
        local_path_allowed: bool = False,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.accepted_ports = self.build_accepted_ports(accepted_ports)
        if "*" in self.accepted_ports:
            self.accepted_ports = None

        self.accepted_protocols = accepted_protocols
        if self.accepted_protocols:
            if not isinstance(self.accepted_protocols, Iterable) or isinstance(self.accepted_protocols, str):
                self.accepted_protocols = set(self.accepted_protocols)
            if "*" in accepted_protocols:
                self.accepted_protocols = None

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

        if not isinstance(local_path_allowed, bool):
            raise ValueError("local_path_allowed must be a boolean")

        self.clean_get_params = clean_get_params
        self.domain_allowed_list = domain_allowed_list
        self.domain_disallowed_list = domain_disallowed_list
        self.local_path_allowed = local_path_allowed

    def build_accepted_ports(self, accepted_ports):
        accepted_ports_value = set()
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

                        if start < 0:
                            raise ValueError("Start value must be greater than zero")

                        if end > 65535:  # 2**16 max ports:
                            raise ValueError("End value must be less or equal than 65535")

                        accepted_ports_value.update(range(start, end + 1))

                    else:
                        accepted_ports_value.add(int(port))
                return accepted_ports_value
        if isinstance(accepted_ports, int):
            if accepted_ports < 0:
                raise ValueError("Port value must be greater than zero")

            if accepted_ports > 65535:  # 2**16 max ports:
                raise ValueError("Port value must be less or equal than 65535")

            accepted_ports_value.add(accepted_ports)
            return accepted_ports_value

        if isinstance(accepted_ports, Iterable):
            for accepted_port in accepted_ports:
                accepted_ports_value |= self.build_accepted_ports(accepted_port)
            return accepted_ports_value

        raise ValueError("accepted_ports must be a iterable or an integer or string")

    def isInvalid(self, value):
        try:
            parsed_url = urlparse(value)
        except ValueError:
            return "Can't parse URL"

        if not self.local_path_allowed and parsed_url.scheme == "":
            return f"""No protocol specified"""

        if self.accepted_ports:
            if parsed_url.port not in self.accepted_ports:
                return f""""{parsed_url.port}" not in the accepted ports."""

        if self.accepted_protocols:
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

        parsed_url = urlparse(value)
        if self.local_path_allowed and parsed_url.scheme == "":
            if value[0] not in "?#/":
                value = f"/{value}"
                parsed_url = urlparse(value)

        if self.clean_get_params:
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
            "accepted_protocols": list(self.accepted_protocols) if self.accepted_protocols else None,
            "accepted_ports": list(self.accepted_ports) if self.accepted_ports else None,
            "clean_get_params": self.clean_get_params,
            "domain_allowed_list": self.domain_allowed_list,
            "domain_disallowed_list": self.domain_disallowed_list,
            "local_path_allowed": self.local_path_allowed,
        }
