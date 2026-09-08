"""Login-abuse throttles, keyed on the client address.

The rates live in `config/settings.py` under `DEFAULT_THROTTLE_RATES`, and
the counters live in their own named cache so that clearing an application
cache cannot reset the control.

Both scopes key on the client address and never on the submitted username.
Keying on a name would let an attacker lock out a named account, and the
different behaviour of a known and an unknown name would leak which accounts
exist. The counters are per process; a multi-process deployment needs the
shared backend tracked in issue 128.
"""

from django.core.cache import caches
from rest_framework.throttling import SimpleRateThrottle

LOGIN_THROTTLE_CACHE_ALIAS = 'login_throttle'


class _LoginRateThrottle(SimpleRateThrottle):
    """One login counter per client address, in the dedicated cache."""

    @property
    def cache(self):
        # Resolved per call rather than bound at import time, so the alias
        # always names the cache the current settings define.
        return caches[LOGIN_THROTTLE_CACHE_ALIAS]

    def get_cache_key(self, request, view):
        # `get_ident` returns the client address alone while `NUM_PROXIES` is
        # 0, so a forged forwarding header cannot buy a fresh allowance.
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request),
        }


class LoginBurstThrottle(_LoginRateThrottle):
    """The short window that stops a rapid guessing burst."""

    scope = 'login_burst'


class LoginSustainedThrottle(_LoginRateThrottle):
    """The long window that stops a slow, patient guessing run."""

    scope = 'login_sustained'
