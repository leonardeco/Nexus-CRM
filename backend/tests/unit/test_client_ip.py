from types import SimpleNamespace
from unittest.mock import MagicMock

from app.core.config import settings
from app.core.http import client_ip


def test_untrusted_peer_ignores_forwarded_for(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trusted_proxy_ips", "")
    request = MagicMock()
    request.client = SimpleNamespace(host="203.0.113.4")
    request.headers.get.return_value = "198.51.100.9"
    assert client_ip(request) == "203.0.113.4"


def test_trusted_cidr_uses_forwarded_client(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trusted_proxy_ips", "10.0.0.0/8,172.16.0.0/12")
    request = MagicMock()
    request.client = SimpleNamespace(host="172.18.0.5")
    request.headers.get.return_value = "203.0.113.10"
    assert client_ip(request) == "203.0.113.10"
