from app.core.errors import AppError

_REDIS_UNAVAILABLE_TITLE = "Servicio no disponible"
_REDIS_UNAVAILABLE_DETAIL = "Intenta de nuevo"


def login_rate_key(email: str, ip: str) -> str:
    return f"rl:login:{email}:{ip}"


def signup_rate_key(ip: str) -> str:
    return f"rl:signup:{ip}"


def resend_rate_key(email: str) -> str:
    return f"rl:resend:{email}"


def password_reset_rate_key(email: str) -> str:
    return f"rl:password-reset:{email}"


def arco_rate_key(slug: str, ip: str) -> str:
    return f"rl:arco:{slug}:{ip}"


def redis_unavailable_error() -> AppError:
    return AppError(
        503,
        "redis_unavailable",
        _REDIS_UNAVAILABLE_TITLE,
        _REDIS_UNAVAILABLE_DETAIL,
    )


async def enforce_rate_limit(
    redis,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    try:
        current = int(await redis.incr(key))
        if current == 1:
            await redis.expire(key, window_seconds)
    except AppError:
        raise
    except Exception as exc:
        raise redis_unavailable_error() from exc
    if current > limit:
        raise AppError(
            429,
            "rate_limited",
            "Demasiados intentos",
            "Intenta de nuevo más tarde.",
        )
