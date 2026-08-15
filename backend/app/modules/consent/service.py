from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ConsentService:
    async def record(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        user_id: UUID,
        policy_version: str,
        ip: str,
        accept_privacy_policy: bool,
        accept_habeas_data: bool,
    ) -> UUID:
        from sqlalchemy import text

        consent_id = uuid4()
        await session.execute(
            text(
                """
                INSERT INTO catalog.consent_records
                    (id, tenant_id, user_id, policy_version,
                     accept_privacy_policy, accept_habeas_data, ip_address)
                VALUES
                    (:id, :tenant_id, :user_id, :policy_version,
                     :accept_privacy, :accept_habeas, :ip)
                """
            ),
            {
                "id": consent_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "policy_version": policy_version,
                "accept_privacy": accept_privacy_policy,
                "accept_habeas": accept_habeas_data,
                "ip": ip,
            },
        )
        return consent_id
