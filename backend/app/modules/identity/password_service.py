import re

from app.core.errors import AppError
from app.core.security import hash_password, verify_password

_UPPER = re.compile(r"[A-Z]")
_LOWER = re.compile(r"[a-z]")
_DIGIT = re.compile(r"[0-9]")


class PasswordService:
    def hash(self, password: str) -> str:
        return hash_password(password)

    def verify(self, password: str, password_hash: str) -> bool:
        return verify_password(password, password_hash)

    def validate_policy(self, password: str) -> None:
        if (
            len(password) < 10
            or _UPPER.search(password) is None
            or _LOWER.search(password) is None
            or _DIGIT.search(password) is None
        ):
            raise AppError(
                422,
                "validation_error",
                "Datos inválidos",
                "La contraseña debe tener al menos 10 caracteres, una mayúscula, una minúscula y un dígito.",
            )
