"""Rate limits for sensitive vault operations."""

from rest_framework.throttling import UserRateThrottle


class VaultUnlockThrottle(UserRateThrottle):
    scope = "vault_unlock"
    rate = "5/min"
