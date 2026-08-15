import asyncio
import secrets
import string
from typing import Literal

import pyotp
from sqlalchemy.orm.attributes import flag_modified

from app.core.errors import AppError
from app.core.security import decrypt_bytes, encrypt_bytes, hash_password, verify_password
from app.modules.identity.models import User

_ALPHABET = string.ascii_uppercase + string.digits
_ISSUER = "NEXUS CRM"


class MfaService:
    def start_enroll(self, email: str) -> tuple[str, bytes]:
        secret = pyotp.random_base32()
        encrypted = encrypt_bytes(secret.encode("utf-8"))
        otpauth_url = pyotp.TOTP(secret).provisioning_uri(
            name=email, issuer_name=_ISSUER
        )
        return otpauth_url, encrypted

    async def enroll(self, user: User, code: str) -> list[str]:
        if not await asyncio.to_thread(self._verify_totp, user, code):
            raise AppError(
                401,
                "mfa_invalid",
                "Código inválido",
                "El código de autenticación no es válido.",
            )
        codes = self._generate_backup_codes()
        user.backup_code_hashes = [
            await asyncio.to_thread(hash_password, item) for item in codes
        ]
        user.mfa_status = "enrolled"
        flag_modified(user, "backup_code_hashes")
        return codes

    async def verify_login(self, user: User, code: str) -> Literal["totp", "backup"]:
        normalized = code.strip().replace(" ", "").replace("-", "")
        if len(normalized) == 6 and normalized.isdigit():
            if await asyncio.to_thread(self._verify_totp, user, normalized):
                return "totp"
            raise AppError(
                401,
                "mfa_invalid",
                "Código inválido",
                "El código de autenticación no es válido.",
            )
        if await self._consume_backup(user, normalized.upper()):
            return "backup"
        raise AppError(
            401,
            "mfa_invalid",
            "Código inválido",
            "El código de autenticación no es válido.",
        )

    def _verify_totp(self, user: User, code: str) -> bool:
        if not user.totp_secret_encrypted:
            return False
        secret = decrypt_bytes(user.totp_secret_encrypted).decode("utf-8")
        return bool(pyotp.TOTP(secret).verify(code, valid_window=0))

    async def _consume_backup(self, user: User, code: str) -> bool:
        hashes = list(user.backup_code_hashes or [])
        for index, hashed in enumerate(hashes):
            if await asyncio.to_thread(verify_password, code, hashed):
                hashes.pop(index)
                user.backup_code_hashes = hashes
                flag_modified(user, "backup_code_hashes")
                return True
        return False

    def _generate_backup_codes(self) -> list[str]:
        return [
            "".join(secrets.choice(_ALPHABET) for _ in range(8)) for _ in range(10)
        ]
