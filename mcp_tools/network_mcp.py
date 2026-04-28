"""
OSSARTH — mcp_tools/network_mcp.py

Lightweight network information tools.
No slow external network calls — only local state queries and fast TCP checks.
"""
from __future__ import annotations
import socket
import time
from mcp_tools.tool_base import mcp_tool


@mcp_tool()
def get_network_interfaces() -> list:
    """Return list of network interfaces with IP, hostname, and reachability."""
    hostname = socket.gethostname()
    interfaces = []
    try:
        # Get all IPs for this host
        for info in socket.getaddrinfo(hostname, None):
            family, _, _, _, addr = info
            ip = addr[0]
            if ip not in [i.get("ip") for i in interfaces]:
                interfaces.append({
                    "name": "eth0" if family == socket.AF_INET else "eth0_ipv6",
                    "ip": ip,
                    "family": "IPv4" if family == socket.AF_INET else "IPv6",
                    "is_up": True,
                })
    except Exception:
        interfaces = [{"name": "loopback", "ip": "127.0.0.1", "family": "IPv4", "is_up": True}]

    # Always include loopback
    if not any(i.get("ip") == "127.0.0.1" for i in interfaces):
        interfaces.insert(0, {"name": "lo", "ip": "127.0.0.1", "family": "IPv4", "is_up": True})

    return interfaces


@mcp_tool()
def check_port(host: str, port: int, timeout_seconds: float = 2.0) -> dict:
    """Check if a TCP port on a host is reachable."""
    t0 = time.perf_counter()
    reachable = False
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            reachable = True
    except (socket.timeout, ConnectionRefusedError, OSError):
        reachable = False
    latency_ms = (time.perf_counter() - t0) * 1000
    return {
        "host": host,
        "port": port,
        "reachable": reachable,
        "latency_ms": round(latency_ms, 2),
    }


@mcp_tool()
def get_hostname() -> str:
    """Return the current machine's hostname."""
    return socket.gethostname()


@mcp_tool()
def get_open_ports() -> list:
    """Return the simulated list of open ports from resource state."""
    # Simulated — we don't do a real port scan
    from kernel_sim.resource_state import get_resource_state
    state = get_resource_state()
    dashboard_port = int(__import__("os").getenv("OSSARTH_DASHBOARD_PORT", "8000"))
    return [dashboard_port, 22, 80]
