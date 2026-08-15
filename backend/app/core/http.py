from fastapi import Request

from app.core.config import settings


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client is not None else "0.0.0.0"
    trusted = {
        item.strip()
        for item in settings.trusted_proxy_ips.split(",")
        if item.strip()
    }
    if peer in trusted:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[-1].strip()
    return peer
