import json
import secrets
import time
from typing import Any
from uuid import UUID, uuid4

from redis.asyncio import Redis

from app.core.config import settings
from app.core.rate_limit import redis_unavailable_error

_SESSION_PREFIX = "sess:"
_CHALLENGE_PREFIX = "mfa:"


class SessionService:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def _ping(self) -> None:
        try:
            await self._redis.ping()
        except Exception as exc:
            raise redis_unavailable_error() from exc

    async def create(
        self,
        principal: dict[str, Any],
        *,
        scope: str,
    ) -> str:
        await self._ping()
        session_id = secrets.token_urlsafe(32)
        payload = {
            **principal,
            "scope": scope,
            "createdAt": time.time(),
        }
        try:
            await self._redis.set(
                f"{_SESSION_PREFIX}{session_id}",
                json.dumps(payload),
                ex=settings.session_idle_seconds,
            )
        except Exception as exc:
            raise redis_unavailable_error() from exc
        return session_id

    async def get(self, session_id: str) -> dict[str, Any] | None:
        await self._ping()
        try:
            raw = await self._redis.get(f"{_SESSION_PREFIX}{session_id}")
        except Exception as exc:
            raise redis_unavailable_error() from exc
        if not raw:
            return None
        data = json.loads(raw)
        created = float(data.get("createdAt") or 0)
        if created and (time.time() - created) > settings.session_ttl_seconds:
            await self.delete(session_id)
            return None
        try:
            await self._redis.expire(
                f"{_SESSION_PREFIX}{session_id}", settings.session_idle_seconds
            )
        except Exception as exc:
            raise redis_unavailable_error() from exc
        return data

    async def delete(self, session_id: str) -> None:
        try:
            await self._redis.delete(f"{_SESSION_PREFIX}{session_id}")
        except Exception as exc:
            raise redis_unavailable_error() from exc

    async def create_mfa_challenge(self, user_id: UUID) -> str:
        await self._ping()
        challenge_id = str(uuid4())
        try:
            await self._redis.set(
                f"{_CHALLENGE_PREFIX}{challenge_id}",
                json.dumps({"userId": str(user_id)}),
                ex=settings.mfa_challenge_ttl_seconds,
            )
        except Exception as exc:
            raise redis_unavailable_error() from exc
        return challenge_id

    async def get_mfa_challenge(self, challenge_id: str) -> dict[str, Any] | None:
        await self._ping()
        try:
            raw = await self._redis.get(f"{_CHALLENGE_PREFIX}{challenge_id}")
        except Exception as exc:
            raise redis_unavailable_error() from exc
        if not raw:
            return None
        return json.loads(raw)

    async def delete_mfa_challenge(self, challenge_id: str) -> None:
        try:
            await self._redis.delete(f"{_CHALLENGE_PREFIX}{challenge_id}")
        except Exception as exc:
            raise redis_unavailable_error() from exc
