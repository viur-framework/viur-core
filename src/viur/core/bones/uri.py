import fnmatch
import typing as t
from . import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
from urllib.parse import urlparse, urlunparse
from collections.abc import Iterable
from collections import namedtuple

PORT_MIN: t.Final[int] = 1
PORT_MAX: t.Final[int] = 2 ** 16 - 1


class UriBone(BaseBone):
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
        """
        The UriBone is used for storing URI and URL.

        :param accepted_protocols: The accepted protocols can be set to allow only the provide protocols.
        :param accepted_ports The accepted ports can be set to allow only the provide ports.
        ..  code-block:: python
            # Example
            UriBone(accepted_ports=1)
            UriBone(accepted_ports="2")
            UriBone(accepted_ports="1-4")
            UriBone(accepted_ports=(1,"2","4-10"))
        :param clean_get_params: When set to True, the GET-parameter for the URL will be cleaned.
        :param domain_allowed_list: If set, only the URLs that are matched with an entry of this iterable
            will be accepted.
        :param domain_disallowed_list: If set, only the URLs that are not matched
            with an entry of this iterable will be accepted.
        :param local_path_allowed: If True, the URLs that are local paths will be prefixed with "/".
        """
        super().__init__(**kwargs)
        if accepted_ports:
            self.accepted_ports = sorted(set(UriBone._build_accepted_ports(accepted_ports)), key=lambda rng: rng.start)

            if range(PORT_MIN, PORT_MAX + 1) in self.accepted_ports:
                self.accepted_ports = None  # all allowed
        else:
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

    @classmethod
    def _build_accepted_ports(cls, accepted_ports: str | int | t.Iterable[str | int]) -> list[range]:
        if isinstance(accepted_ports, str):
            if accepted_ports == "*":
                return [range(PORT_MIN, PORT_MAX + 1)]

            elif "," in accepted_ports:  # list of ranges, values
                return cls._build_accepted_ports([
                    value.strip() for value in accepted_ports.split(",")
                ])

            elif "-" in accepted_ports:  # range of ports
                start, end = accepted_ports.split("-", 1)
                start = int(start)
                end = int(end)
                if start > end:
                    raise ValueError("Start value must be less than end value")

                if start < PORT_MIN:
                    raise ValueError("Start value must be greater than zero")

                if end > PORT_MAX:
                    raise ValueError(f"End value must be less or equal than {PORT_MAX}")

                return [range(start, end + 1)]

            else:
                port = int(accepted_ports)
                return [range(port, port + 1)]

        elif isinstance(accepted_ports, int):
            if accepted_ports < PORT_MIN:
                raise ValueError("Port value must be greater than zero")

            if accepted_ports > PORT_MAX:
                raise ValueError(f"Port value must be less or equal than {PORT_MAX}")

            return [range(accepted_ports, accepted_ports + 1)]

        elif isinstance(accepted_ports, Iterable):
            accepted_ports_value = []
            for accepted_port in accepted_ports:
                accepted_ports_value.extend(UriBone._build_accepted_ports(accepted_port))
            return accepted_ports_value

        raise ValueError("accepted_ports must be a iterable or an integer or string")

    def isInvalid(self, value) -> str | None:
        try:
            parsed_url = urlparse(value)
        except ValueError:
            return "Can't parse URL"

        if not self.local_path_allowed and parsed_url.scheme == "":
            return f"""No protocol specified"""

        if self.accepted_ports:
            if not any(parsed_url.port in rng for rng in self.accepted_ports):
                return f""""{parsed_url.port}" not in the accepted ports."""

        if self.accepted_protocols:
            for protocol in self.accepted_protocols:
                if fnmatch.fnmatch(parsed_url.scheme, protocol):
                    break
            else:
                return f""""{parsed_url.scheme}" not in the accepted protocols."""

        if self.domain_allowed_list is not None:
            if parsed_url.hostname:
                for domain in self.domain_allowed_list:
                    if fnmatch.fnmatch(parsed_url.hostname, domain) or domain in parsed_url.hostname:
                        break
                else:
                    return f"""Provided URL is not in the domain allowed list."""
            else:
                return f"""Provided URL has no hostname specified."""

        if self.domain_disallowed_list is not None:
            if parsed_url.hostname:
                for domain in self.domain_disallowed_list:
                    if fnmatch.fnmatch(parsed_url.hostname, domain) or domain in parsed_url.hostname:
                        return f"""Provided URL is in the domain disallowed list."""

            else:
                return f"""Provided URL has no hostname specified."""

    def singleValueFromClient(self, value, skel, bone_name, client_data) -> tuple:
        if err := self.isInvalid(value):
            return value, [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

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
            "accepted_ports": [(rng.start, rng.stop) for rng in self.accepted_ports] if self.accepted_ports else None,
            "clean_get_params": self.clean_get_params,
            "domain_allowed_list": self.domain_allowed_list,
            "domain_disallowed_list": self.domain_disallowed_list,
            "local_path_allowed": self.local_path_allowed,
        }
