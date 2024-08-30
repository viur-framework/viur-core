from . import RawBone
from urllib.parse import urlparse

class URIBone(RawBone):
    type = "uri"

    def __init__(
        self,
        *,
        accepted_protocol: str | list[str] | None = None,
        accepted_ports: int | str | list[int] | list[str] = "*",
        **kwargs
    ):
        super().__init__(**kwargs)
        self.accepted_ports = self.build_accepted_ports(accepted_ports)
        if "*" in self.accepted_ports:
            self.accepted_ports = "*"

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
        if isinstance(accepted_ports, list):
            for accepted_port in accepted_ports:
                accepted_ports_value.extend(self.build_accepted_ports(accepted_port))
            return accepted_ports_value


    def isInvalid(self, value):
        try:
            parsed_url=urlparse(value)
        except ValueError:
            return "Can't parse URL"

        if self.accepted_ports!="*":
            if parsed_url.port not in self.accepted_ports:
                return f""""{parsed_url.port}" not in the accepted ports"""
    def structure(self) -> dict:
        return  super().structure() | {
            "accepted_ports": self.accepted_ports,
        }
