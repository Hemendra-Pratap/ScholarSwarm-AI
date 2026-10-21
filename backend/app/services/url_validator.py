import ipaddress
import re
import socket
import urllib.parse
from collections.abc import Callable


FORBIDDEN_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),       # CGNAT / Shared space
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local (includes 169.254.169.254)
    ipaddress.ip_network("172.16.0.0/12"),      # Private
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),       # TEST-NET-1
    ipaddress.ip_network("192.88.99.0/24"),     # 6to4 relay
    ipaddress.ip_network("192.168.0.0/16"),     # Private
    ipaddress.ip_network("198.18.0.0/15"),      # Benchmarking
    ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved
    ipaddress.ip_network("255.255.255.255/32"), # Broadcast
    # IPv6 ranges
    ipaddress.ip_network("::/128"),             # Unspecified
    ipaddress.ip_network("::1/128"),            # Loopback
    ipaddress.ip_network("fc00::/7"),           # Unique local (ULA)
    ipaddress.ip_network("fe80::/10"),          # Link-local
    ipaddress.ip_network("ff00::/8"),           # Multicast
    ipaddress.ip_network("2001:db8::/32"),      # Documentation
]

FORBIDDEN_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "instance-data",
    "metadata.nic.google",
    "metadata",
}

FORBIDDEN_DOMAIN_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".arpa",
    ".lan",
    ".home",
    ".corp",
)

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}


def default_dns_resolver(host: str, port: int) -> list[str]:
    """Default system DNS resolver returning list of resolved IP strings."""
    clean_host = host.strip("[]")
    results = socket.getaddrinfo(clean_host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(r[4][0] for r in results))


class URLValidationError(ValueError):
    """Raised when a URL violates security or SSRF constraints."""
    pass


class URLValidator:
    """Security validator protecting against SSRF, internal destination access, and malformed URLs."""

    @classmethod
    def parse_alternative_ip(cls, host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
        """Parse alternative IP representations (integer, hex, octal, IPv4-mapped IPv6)."""
        clean = host.strip("[]").strip()
        
        # Pure numeric integer IP (e.g., 2130706433 = 127.0.0.1)
        if clean.isdigit():
            try:
                val = int(clean)
                if 0 <= val <= 0xFFFFFFFF:
                    return ipaddress.IPv4Address(val)
            except Exception:
                pass

        # Hexadecimal IP (e.g., 0x7f000001 = 127.0.0.1)
        if clean.lower().startswith("0x"):
            try:
                val = int(clean, 16)
                if 0 <= val <= 0xFFFFFFFF:
                    return ipaddress.IPv4Address(val)
            except Exception:
                pass

        # Dotted quad with potential octal parts (e.g. 0177.0.0.1)
        if re.match(r"^[0-9]+(?:\.[0-9]+){1,3}$", clean):
            parts = clean.split(".")
            parsed_parts = []
            for p in parts:
                try:
                    if p.startswith("0") and len(p) > 1:
                        # Octal representation
                        parsed_parts.append(int(p, 8))
                    else:
                        parsed_parts.append(int(p))
                except Exception:
                    return None
            if len(parsed_parts) == 4 and all(0 <= p <= 255 for p in parsed_parts):
                try:
                    return ipaddress.IPv4Address(".".join(str(p) for p in parsed_parts))
                except Exception:
                    pass

        # Standard IPv4 or IPv6
        try:
            ip = ipaddress.ip_address(clean)
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                return ip.ipv4_mapped
            return ip
        except ValueError:
            pass

        return None

    @classmethod
    def is_ip_allowed(cls, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> tuple[bool, str]:
        """Verify whether an IP address is a safe, globally reachable public address."""
        # Unwrap IPv4-mapped IPv6 address
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped

        # Basic properties
        if ip.is_loopback:
            return False, f"Loopback address '{ip}' is blocked."
        if ip.is_private:
            return False, f"Private address '{ip}' is blocked."
        if ip.is_link_local:
            return False, f"Link-local address '{ip}' is blocked."
        if ip.is_multicast:
            return False, f"Multicast address '{ip}' is blocked."
        if ip.is_reserved:
            return False, f"Reserved address '{ip}' is blocked."
        if ip.is_unspecified:
            return False, f"Unspecified address '{ip}' is blocked."

        # Check explicit forbidden network list (CGNAT, testnets, etc.)
        for net in FORBIDDEN_NETWORKS:
            if ip in net:
                return False, f"Address '{ip}' is within restricted network '{net}'."

        # Ensure global reachability
        if not ip.is_global:
            return False, f"Address '{ip}' is not globally routable."

        return True, ""

    @classmethod
    def validate_url(
        cls,
        url: str,
        dns_resolver: Callable[[str, int], list[str]] | None = None,
    ) -> tuple[str, list[str]]:
        """Validate URL for public HTTP/HTTPS access, applying strict SSRF protections.
        
        Returns:
            tuple[str, list[str]]: Normalized URL and list of resolved validated IP strings.
            
        Raises:
            URLValidationError: If URL violates any security constraint.
        """
        if not url or not isinstance(url, str):
            raise URLValidationError("Target URL must be a non-empty string.")

        url_clean = url.strip()
        try:
            parsed = urllib.parse.urlsplit(url_clean)
        except Exception:
            raise URLValidationError("Malformed URL format.")

        # 1. Scheme validation
        scheme = parsed.scheme.lower()
        if scheme not in ALLOWED_SCHEMES:
            raise URLValidationError(f"Unsupported URL scheme '{scheme}'. Only HTTP and HTTPS are permitted.")

        # 2. Reject embedded userinfo / credentials
        if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
            raise URLValidationError("Embedded credentials in URLs are forbidden.")

        # 3. Hostname validation
        raw_host = parsed.hostname
        if not raw_host:
            raise URLValidationError("URL does not contain a valid hostname.")

        host = raw_host.lower().rstrip(".")
        if not host:
            raise URLValidationError("URL hostname is empty.")

        # 4. Check forbidden hostname keywords and suffixes
        if host in FORBIDDEN_HOSTNAMES:
            raise URLValidationError(f"Access to hostname '{host}' is forbidden.")

        for suffix in FORBIDDEN_DOMAIN_SUFFIXES:
            if host.endswith(suffix):
                raise URLValidationError(f"Access to domain '{host}' with suffix '{suffix}' is forbidden.")

        # 5. Port validation
        port = parsed.port
        if port is None:
            port = 443 if scheme == "https" else 80
        elif port not in ALLOWED_PORTS:
            raise URLValidationError(f"Port {port} is not allowed. Only ports 80 and 443 are supported.")

        # 6. Check if host is an explicit or alternative IP address
        direct_ip = cls.parse_alternative_ip(host)
        if direct_ip:
            allowed, reason = cls.is_ip_allowed(direct_ip)
            if not allowed:
                raise URLValidationError(f"Destination IP '{direct_ip}' is blocked: {reason}")
            resolved_ips = [str(direct_ip)]
        else:
            # 7. DNS resolution and IP validation
            resolver = dns_resolver or default_dns_resolver
            try:
                resolved_ips = resolver(host, port)
            except Exception as e:
                raise URLValidationError(f"Unable to resolve hostname '{host}': DNS resolution failed.") from e

            if not resolved_ips:
                raise URLValidationError(f"Unable to resolve hostname '{host}': No IP addresses returned.")

            # Check every resolved IP address
            for ip_str in resolved_ips:
                try:
                    ip_obj = ipaddress.ip_address(ip_str.strip("[]"))
                except ValueError:
                    raise URLValidationError(f"Invalid resolved IP '{ip_str}' for hostname '{host}'.")

                allowed, reason = cls.is_ip_allowed(ip_obj)
                if not allowed:
                    raise URLValidationError(f"Hostname '{host}' resolves to forbidden IP '{ip_str}': {reason}")

        # Return reconstructed canonical URL and resolved IPs
        # (Preserve path, query, and fragment cleanly)
        canonical_netloc = host if (parsed.port is None or parsed.port in (80, 443)) else f"{host}:{parsed.port}"
        normalized_url = urllib.parse.urlunsplit((
            scheme,
            canonical_netloc,
            parsed.path or "/",
            parsed.query,
            parsed.fragment,
        ))

        return normalized_url, resolved_ips
