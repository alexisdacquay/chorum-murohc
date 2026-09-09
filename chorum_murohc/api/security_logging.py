"""Minimal structured logging for refused requests (S-04).

Nothing in this project logged anything before this. A burst of refused
logins, forged requests, or cross-role reads left no trace outside the
product audit table, which records successful mutations, not refused
attempts.

Every refusal this module logs carries exactly four fields: which control
refused, the HTTP method, the path, and the status code. Never a username, a
password, a PIN, a token, a household name, or any other product content -
the same "no secret, no household content" rule `_docs/design.md` already
sets for audit context and operational logs generally.

Three refusal paths reach this module:

- DRF raises `PermissionDenied` for both a permission-matrix denial (the
  `IsHouseholdParent` / `IsHouseholdChild` primitives in `permissions.py`)
  and a CSRF failure (`SessionAuthentication.enforce_csrf`, which this
  project's DRF views use instead of Django's own CSRF middleware, since
  every DRF view is CSRF-exempt at the Django layer by design). DRF raises
  `NotAuthenticated` for a signed-out caller, which this project's
  `exception_handler` (see `rest_framework.views.exception_handler`) turns
  into the same 403 an unauthenticated `SessionAuthentication` caller always
  gets. `logging_exception_handler` below wraps the DRF default so every one
  of these is logged in one place, with no endpoint aware it is happening.
- The login throttle raises `Throttled` the same way, so a throttled login
  is logged here too.
- A failed login with a well-formed request never raises an exception (it is
  an ordinary 400 `Response`), so `LoginView.login_failed` in `session.py`
  calls `log_refusal` directly.
"""

import logging

from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger('chorum_murohc.security')

# The status codes a refusal can carry: unauthenticated or forbidden (which
# covers both a permission-matrix denial and a CSRF failure, since DRF raises
# the same exception for each) and throttled.
REFUSAL_STATUS_CODES = frozenset({401, 403, 429})


def log_refusal(request, status_code, event):
    """Log the one line every refusal path writes.

    `event` is a short label naming which control refused (an exception
    class name, or 'login_failed'), never a value the caller submitted.
    """
    logger.info(
        'refused request: event=%s method=%s path=%s status=%s',
        event,
        request.method,
        request.path,
        status_code,
    )


def logging_exception_handler(exc, context):
    """The project's `DEFAULT_EXCEPTION_HANDLER`.

    Behaviour is DRF's own `exception_handler`, unchanged; this only adds one
    log line when the resulting response is a refusal.
    """
    response = drf_exception_handler(exc, context)
    if response is not None and response.status_code in REFUSAL_STATUS_CODES:
        request = context.get('request')
        if request is not None:
            log_refusal(request, response.status_code, type(exc).__name__)
    return response
