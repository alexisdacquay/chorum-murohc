"""Session endpoints: sign in, sign out, inspect and switch the active
household.

Same-origin Django sessions and CSRF only, as required by the `Session and
CSRF Policy` and the permission matrix in `_docs/design.md`. There is no JWT,
bearer token, cross-origin credential flow, or browser-stored token here.

Four endpoints under `/api/v1/auth/`:

- `GET session/` is open to everyone, always answers 200, and delivers the
  CSRF cookie a browser needs before it can make an unsafe call.
- `POST login/` takes a username and a password. CSRF is required even though
  the caller is anonymous, and the session identifier is rotated on success.
- `POST logout/` is authenticated and CSRF-protected, flushes the session,
  and answers 204 with no body.
- `GET household/` lists the caller's own live memberships, and
  `POST household/` selects one of them as the active household for the rest
  of the session (issue #130). Both are authenticated only; an unauthenticated
  caller has no memberships to list or select.

Nothing durable is cached in the session except one thing: which household a
caller with more than one live membership has chosen to act in. `is_active`,
the membership, the role, and the household itself are still read from the
database on every request through the shared permission primitive, so a
deactivated account, a deleted membership, or a changed role takes effect on
the very next request even after a household has been selected.

Authority fails closed. Zero memberships, more than one candidate household
with none selected, a selected household the caller is no longer a live
member of, a deleted membership, or a role outside `parent` and `child` all
resolve to a null household and a null role rather than to a guess, and roles
are never unioned across households: selecting a household re-derives the
role from that one membership alone. Every login failure answers with one
identical generic detail, so no response reveals whether an account exists.

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
from rest_framework.exceptions import NotFound, ParseError, Throttled
from rest_framework.permissions import SAFE_METHODS, AllowAny, BasePermission
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from chorum_murohc.api.permissions import resolve_membership
from chorum_murohc.api.security_logging import log_refusal
from chorum_murohc.api.serializers import HouseholdSelectionSerializer, LoginSerializer
from chorum_murohc.api.throttling import LoginBurstThrottle, LoginSustainedThrottle
from chorum_murohc.identity.models import Household, Membership

# The session key holding the household a multi-membership caller has chosen
# to act in. Never trusted on its own: every read re-confirms a live
# membership through `resolve_membership` before it is honoured.
ACTIVE_HOUSEHOLD_SESSION_KEY = 'active_household_id'

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


def _selected_membership(user, request):
    """Return the membership for a session-selected household, or `None`.

    Reads only `request.session`, never a body, query parameter, path value,
    or header: the exact rule every other permission check in this package
    already follows. A missing request, no stored selection, a value that
    does not name a household, or a household the user is no longer a live
    member of are all treated as no selection, so the caller falls through to
    the single-membership default rather than getting stuck on a choice that
    no longer holds.
    """
    session = getattr(request, 'session', None) if request is not None else None
    if session is None:
        return None

    selected_id = session.get(ACTIVE_HOUSEHOLD_SESSION_KEY)
    if selected_id is None:
        return None

    try:
        household = Household.objects.get(pk=selected_id)
    except (Household.DoesNotExist, ValueError, TypeError):
        return None

    membership = resolve_membership(user, household)
    if membership is None or membership.role not in SUPPORTED_ROLES:
        return None
    return membership


def resolve_active_membership(user, request=None):
    """Return the one membership `user` may act through, or `None`.

    The household is never taken from the caller as authority. A caller with
    exactly one live membership always acts through it. A caller with more
    than one live membership acts through whichever one they most recently
    selected with `POST auth/household/`, held in `request.session`, as long
    as that membership is still live; with no selection, or a selection that
    no longer resolves, two or more candidate households is ambiguous and
    fails closed exactly as it always has.

    `request` is optional so every existing caller that only has a user in
    hand keeps working unchanged; passing it is what makes an explicit
    household selection take effect. Every ambiguous or unsupported state
    returns `None`: no user, an unauthenticated or inactive user, zero
    memberships, two or more unresolved candidate households, or a role
    outside `parent` and `child`.
    """
    if user is None or not user.is_authenticated or not user.is_active:
        return None
    if user.pk is None:
        return None

    selected = _selected_membership(user, request)
    if selected is not None:
        return selected

    # Two rows are enough to know the context is ambiguous, and one row is
    # only a candidate until the primitive confirms it.
    candidates = list(Household.objects.filter(memberships__user=user)[:2])
    if len(candidates) != 1:
        return None

    membership = resolve_membership(user, candidates[0])
    if membership is None or membership.role not in SUPPORTED_ROLES:
        return None
    return membership


def available_households(user):
    """The households `user` may switch into: own live memberships only.

    A list of `{id, name, role}` dicts, ordered by household name then id so
    the result is stable. Zero, one, or many rows all answer the same shape;
    this never returns another user's membership or anything beyond the three
    named fields.
    """
    if user is None or not user.is_authenticated or not user.is_active:
        return []
    if user.pk is None:
        return []

    memberships = (
        Membership.objects.filter(user=user, role__in=SUPPORTED_ROLES)
        .select_related('household')
        .order_by('household__name', 'household_id')
    )
    return [
        {
            'id': membership.household.pk,
            'name': membership.household.name,
            'role': membership.role,
        }
        for membership in memberships
    ]


def current_session(user, request=None):
    """Build the exact current-user body for `user`.

    Four keys, always the same four, and never an email address, a password
    hash, a PIN, a session identifier, a CSRF value, a platform staff flag,
    or a second household. `request` is threaded through to
    `resolve_active_membership` only so a caller who has selected a household
    among several sees that one; omitting it answers exactly as it always has
    for a single-membership user.
    """
    if user is None or not user.is_authenticated or not user.is_active:
        return dict(SIGNED_OUT_SESSION)

    body = {
        'is_authenticated': True,
        'user': {'id': user.pk, 'username': user.get_username()},
        'household': None,
        'role': None,
    }

    membership = resolve_active_membership(user, request)
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
        return Response(current_session(request.user, request))


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
        # identifier can never survive a login. The flush also clears any
        # household selection the previous session held, which matters when
        # a second account signs in on the same browser.
        http_request.session.flush()
        start_session(http_request, user)
        return Response(current_session(user, request))


class LogoutView(_SessionAPIView):
    """`POST /api/v1/auth/logout/`: end the caller's own session."""

    http_method_names = ('post', 'options')
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsActiveAuthenticatedUser,)

    def post(self, request):
        # Flushes the session record and rotates the CSRF token.
        end_session(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class HouseholdSwitchView(_SessionAPIView):
    """`GET`/`POST /api/v1/auth/household/`: list and select the active
    household (issue #130).

    Both methods are authenticated only; an unauthenticated caller has no
    memberships of their own to list or select, so it answers exactly like
    every other protected route rather than inventing a public shape.

    `GET` lists the caller's own live memberships, exactly the permission
    matrix row "Select or resolve active household": "Allow only among own
    live memberships". `POST` takes one of those household ids and, only
    after `resolve_membership` confirms it is still a live membership of the
    caller, records it in `request.session`. The id only ever selects a
    candidate; it is never trusted as proof of access, and a foreign or
    unknown id gets the same generic not-found either way, so this cannot be
    used to probe which household ids exist.

    A single-membership caller never needs this: `resolve_active_membership`
    already resolves the one household unambiguously. Calling it anyway is
    harmless, selects that same household, and changes nothing else.
    """

    http_method_names = ('get', 'post', 'options')
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsActiveAuthenticatedUser,)

    def get(self, request):
        return Response({'households': available_households(request.user)})

    def post(self, request):
        serializer = HouseholdSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        household = Household.objects.filter(
            pk=serializer.validated_data['household_id']
        ).first()
        membership = None
        if household is not None:
            membership = resolve_membership(request.user, household)
        if membership is None or membership.role not in SUPPORTED_ROLES:
            # Identical whether the id belongs to someone else's household
            # or does not exist at all (invariant 7): neither confirms nor
            # denies that the id is real.
            raise NotFound()

        request.session[ACTIVE_HOUSEHOLD_SESSION_KEY] = household.pk
        return Response(current_session(request.user, request))


def _login_failed():
    return Response(
        {'detail': LOGIN_FAILED_DETAIL},
        status=status.HTTP_400_BAD_REQUEST,
    )
