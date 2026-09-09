"""Session endpoints: sign in, sign out, and inspect the current user.

Same-origin Django sessions and CSRF only, as required by the `Session and
CSRF Policy` and the permission matrix in `_docs/design.md`. There is no JWT,
bearer token, cross-origin credential flow, or browser-stored token here.

Three endpoints under `/api/v1/auth/`:

- `GET session/` is open to everyone, always answers 200, and delivers the
  CSRF cookie a browser needs before it can make an unsafe call.
- `POST login/` takes a username and a password. CSRF is required even though
  the caller is anonymous, and the session identifier is rotated on success.
- `POST logout/` is authenticated and CSRF-protected, flushes the session,
  and answers 204 with no body.

Nothing durable is cached in the session. `is_active`, the membership, the
role, and the household are read from the database on every request through
the shared permission primitive, so a deactivated account, a deleted
membership, or a changed role takes effect on the very next request.

Authority fails closed. Zero memberships, more than one candidate household,
a deleted membership, or a role outside `parent` and `child` all resolve to a
null household and a null role rather than to a guess, and roles are never
unioned across households. Every login failure answers with one identical
generic detail, so no response reveals whether an account exists.

The login abuse control counts failed attempts only. A caller already over
the limit is refused before any authentication work; a login that succeeds
spends nothing. Every refused login also writes one non-secret log line
through `chorum_murohc.api.security_logging` (S-04).
"""

from django.contrib.auth import authenticate
from django.contrib.auth import login as start_session
from django.contrib.auth import logout as end_session
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ParseError, Throttled
from rest_framework.permissions import SAFE_METHODS, AllowAny, BasePermission
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from chorum_murohc.api.permissions import resolve_membership
from chorum_murohc.api.security_logging import log_refusal
from chorum_murohc.api.serializers import LoginSerializer
from chorum_murohc.api.throttling import LoginBurstThrottle, LoginSustainedThrottle
from chorum_murohc.identity.models import Household, Membership

# The one body returned to every caller who is not a signed-in active user.
SIGNED_OUT_SESSION = {
    'is_authenticated': False,
    'user': None,
    'household': None,
    'role': None,
}

# The one detail returned for every login failure, so that a wrong password,
# an unknown username, a disabled account, and a malformed body are
# indistinguishable.
LOGIN_FAILED_DETAIL = 'Unable to log in with the credentials provided.'

# The one detail returned when the login throttle refuses a request. It
# carries no wait hint and no account information.
LOGIN_THROTTLED_DETAIL = 'Too many login attempts. Try again later.'

# The only roles this contract can return. Anything else fails closed.
SUPPORTED_ROLES = frozenset({Membership.Role.PARENT, Membership.Role.CHILD})


def resolve_active_membership(user):
    """Return the one membership `user` may act through, or `None`.

    The household is never taken from the caller. It is the single household
    the user is a live member of, confirmed through the shared permission
    primitive. Every ambiguous or unsupported state returns `None`: no user,
    an unauthenticated or inactive user, zero memberships, two or more
    candidate households, or a role outside `parent` and `child`.
    """
    if user is None or not user.is_authenticated or not user.is_active:
        return None
    if user.pk is None:
        return None

    # Two rows are enough to know the context is ambiguous, and one row is
    # only a candidate until the primitive confirms it.
    candidates = list(Household.objects.filter(memberships__user=user)[:2])
    if len(candidates) != 1:
        return None

    membership = resolve_membership(user, candidates[0])
    if membership is None or membership.role not in SUPPORTED_ROLES:
        return None
    return membership


def current_session(user):
    """Build the exact current-user body for `user`.

    Four keys, always the same four, and never an email address, a password
    hash, a PIN, a session identifier, a CSRF value, a platform staff flag,
    or a second household.
    """
    if user is None or not user.is_authenticated or not user.is_active:
        return dict(SIGNED_OUT_SESSION)

    body = {
        'is_authenticated': True,
        'user': {'id': user.pk, 'username': user.get_username()},
        'household': None,
        'role': None,
    }

    membership = resolve_active_membership(user)
    if membership is not None:
        household = membership.household
        body['household'] = {'id': household.pk, 'name': household.name}
        body['role'] = membership.role
    return body


class HasValidCsrfToken(BasePermission):
    """Require a valid CSRF token on every unsafe method.

    `SessionAuthentication` checks CSRF only once it has authenticated a
    session user, so an anonymous login post would otherwise skip the check
    entirely. This runs the same framework check for anonymous callers too.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        # Raises `PermissionDenied` with the framework's generic reason, which
        # never contains the token itself.
        SessionAuthentication().enforce_csrf(request)
        return True


class IsActiveAuthenticatedUser(BasePermission):
    """Allow only a signed-in user whose account is still active."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active)


class _SessionAPIView(APIView):
    """Shared behaviour for the three session endpoints.

    Each endpoint declares the methods it supports, and an unsupported one is
    refused before authority is considered, so the answer to a safe method
    never depends on who is asking and no handler can run for a method the
    endpoint does not define.
    """

    renderer_classes = (JSONRenderer,)

    def initial(self, request, *args, **kwargs):
        if request.method.lower() not in self.http_method_names:
            self.http_method_not_allowed(request)
        super().initial(request, *args, **kwargs)


class SessionView(_SessionAPIView):
    """`GET /api/v1/auth/session/`: who the caller is, and the CSRF cookie."""

    http_method_names = ('get', 'head', 'options')
    authentication_classes = (SessionAuthentication,)
    permission_classes = (AllowAny,)

    def get(self, request):
        # The cookie is set on the underlying request so that the CSRF
        # middleware, which never sees the framework wrapper, delivers it.
        get_token(request._request)
        return Response(current_session(request.user))


class LoginView(_SessionAPIView):
    """`POST /api/v1/auth/login/`: exchange a username and password."""

    http_method_names = ('post', 'options')
    authentication_classes = ()
    permission_classes = (HasValidCsrfToken,)
    throttle_classes = (LoginBurstThrottle, LoginSustainedThrottle)

    def initial(self, request, *args, **kwargs):
        # Read the brake before anything touches the body: the CSRF permission
        # check parses it, so a caller already over the limit must be refused
        # here rather than answered with a parse failure. Reading spends
        # nothing, so the framework's own later check reads the same answer.
        if request.method == 'POST':
            self.check_throttles(request)
        super().initial(request, *args, **kwargs)

    def throttled(self, request, wait):
        # One fixed body with no wait hint, so a refusal says nothing about
        # the submitted username or about how much allowance is left.
        raise Throttled(detail=LOGIN_THROTTLED_DETAIL)

    def handle_exception(self, exc):
        # A body this endpoint cannot parse is answered with the same generic
        # failure as any other, and counts as one failed attempt. The CSRF
        # check reads the body first, so the parse can fail before the handler
        # is ever reached.
        if isinstance(exc, ParseError):
            return self.login_failed()
        return super().handle_exception(exc)

    def login_failed(self):
        """Answer the one generic failure and spend one unit of allowance.

        Every way a login can fail comes through here, so an unknown
        username, a wrong password, a disabled account, an invalid body and
        an unparseable body each record exactly one attempt against both the
        burst and the sustained scope.
        """
        for throttle in self.get_throttles():
            throttle.record_failure(self.request, self)
        log_refusal(self.request, status.HTTP_400_BAD_REQUEST, 'login_failed')
        return _login_failed()

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return self.login_failed()

        http_request = request._request
        user = authenticate(
            request=http_request,
            username=serializer.validated_data['username'],
            password=serializer.validated_data['password'],
        )
        if user is None or not user.is_active:
            return self.login_failed()

        # Rotate the session identifier: the one the caller arrived with is
        # destroyed before the authenticated one is created, so a fixated
        # identifier can never survive a login.
        http_request.session.flush()
        start_session(http_request, user)
        return Response(current_session(user))


class LogoutView(_SessionAPIView):
    """`POST /api/v1/auth/logout/`: end the caller's own session."""

    http_method_names = ('post', 'options')
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsActiveAuthenticatedUser,)

    def post(self, request):
        # Flushes the session record and rotates the CSRF token.
        end_session(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _login_failed():
    return Response(
        {'detail': LOGIN_FAILED_DETAIL},
        status=status.HTTP_400_BAD_REQUEST,
    )
