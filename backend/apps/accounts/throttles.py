"""IP-based login and setup throttles."""

from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    scope = "login"
    rate = "20/min"


class SetupRateThrottle(AnonRateThrottle):
    scope = "setup"
    rate = "5/min"
