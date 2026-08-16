from enum import StrEnum


class Permission(StrEnum):
    TENANT_SETTINGS_READ = "tenant.settings.read"
    TENANT_SETTINGS_WRITE = "tenant.settings.write"
    USERS_READ = "users.read"
    USERS_INVITE = "users.invite"
    USERS_MANAGE = "users.manage"
    ARCO_INBOX_READ = "arco.inbox.read"
    ARCO_INBOX_WRITE = "arco.inbox.write"
    AUDIT_READ = "audit.read"
    CONTACTS_READ = "contacts.read"
    CONTACTS_WRITE = "contacts.write"
    PIPELINE_READ = "pipeline.read"
    DEAL_WRITE = "deal.write"
    PIPELINE_MANAGE = "pipeline.manage"
    PROFILE_READ = "profile.read"
    PROFILE_WRITE = "profile.write"
