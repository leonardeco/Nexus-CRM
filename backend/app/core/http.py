import ipaddress

from fastapi import Request

from app.core.config import settings


def _peer_is_trusted(peer: str, trusted_items: set[str]) -> bool:
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return peer in trusted_items
    for item in trusted_items:
        try:
            if "/" in item:
                if address in ipaddress.ip_network(item, strict=False):
                    return True
            elif address == ipaddress.ip_address(item):
                return True
        except ValueError:
            if peer == item:
                return True
    return False


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client is not None else "0.0.0.0"
    trusted = {
        item.strip()
        for item in settings.trusted_proxy_ips.split(",")
        if item.strip()
    }
    if _peer_is_trusted(peer, trusted):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[-1].strip()
    return peer
