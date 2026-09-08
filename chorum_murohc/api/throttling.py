"""Login-abuse throttles, keyed on the client address.

The control counts FAILED login attempts only: 10 per minute and 100 per
hour per client address. A login that succeeds is not an attack and spends
nothing, so a household sharing one address cannot lock itself out by
signing its members in.

`SimpleRateThrottle.allow_request` both checks and records, which would
count every attempt including the successful ones. These classes therefore
split the two halves: `allow_request` only reads the counter, and
`record_failure` is the one place that ever writes to it. The login view
calls `record_failure` on its failure path alone.

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

    def allow_request(self, request, view):
        """Read the allowance without spending it.

        Unlike the base class this records nothing, so calling it is free and
        repeatable. `self.now` and `self.history` are still set because the
        framework asks a refusing throttle for its `wait()`.
        """
        if self.rate is None:
            return True

        self.key = self.get_cache_key(request, view)
        if self.key is None:
            return True

        self.now = self.timer()
        self.history = self._recent_attempts(self.key, self.now)
        return len(self.history) < self.num_requests

    def record_failure(self, request, view=None):
        """Spend one unit of the allowance for one failed login attempt."""
        if self.rate is None:
            return

        key = self.get_cache_key(request, view)
        if key is None:
            return

        now = self.timer()
        history = self._recent_attempts(key, now)
        # Newest first, which is the order the base class stores and expires.
        history.insert(0, now)
        self.cache.set(key, history, self.duration)

    def _recent_attempts(self, key, now):
        """The stored attempts that are still inside the rate window."""
        history = self.cache.get(key, [])
        while history and history[-1] <= now - self.duration:
            history.pop()
        return history


class LoginBurstThrottle(_LoginRateThrottle):
    """The short window that stops a rapid guessing burst."""

    scope = 'login_burst'


class LoginSustainedThrottle(_LoginRateThrottle):
    """The long window that stops a slow, patient guessing run."""

    scope = 'login_sustained'
