"""Self-service password change: `POST /api/v1/auth/password/` (issue #129).

One route, one operation: always changes the caller's own account password,
gated on the caller's own current password. Parent-only, matching the
approved contract's decision that self-service applies to a parent
("A parent must be able to change their own password"): a child with a
forgotten password has no account password to prove, and is handled instead
by a parent using the reset route in `chorum_murohc.api.members`.

Every write is same-origin session authenticated and CSRF-protected exactly
like every other mutation in this package. The acting user comes from
`resolve_active_membership`, re-read inside the transaction, never from the
request body.

`chorum_murohc.identity.services.change_own_password` does the real work,
including the audit event; this module's only job is turning its two
exceptions into compact responses, and keeping the caller's own session alive
across its own password change. Django invalidates a session whose password
hash no longer matches on the very next request (session invalidation on
password change); `update_session_auth_hash` re-signs this request's session
immediately after a successful change so the acting parent is not logged out
by their own request. A password reset of a *different* member carries no
such call, in `chorum_murohc.api.members`: that member's existing sessions are
meant to end.
"""

from django.contrib.auth import update_session_auth_hash
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from chorum_murohc.api.permissions import PERMISSION_DENIED_DETAIL, IsHouseholdParent
from chorum_murohc.api.session import resolve_active_membership
from chorum_murohc.identity.models import Membership
from chorum_murohc.identity.services import (
    PasswordMismatchError,
    PasswordWeakError,
    change_own_password,
)

# The one detail returned when the current password does not match. It never
# echoes the submitted value.
PASSWORD_INCORRECT_DETAIL = 'Enter your current account password correctly.'


class PasswordChangeSerializer(serializers.Serializer):
    """The only writable body a change may send: current and new password.

    Both are write-only, so neither can be echoed back in a response or a
    validation error.
    """

    current_password = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=False,
        write_only=True,
    )
    new_password = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=False,
        write_only=True,
    )


class PasswordChangeView(APIView):
    """`POST /api/v1/auth/password/`: change the caller's own password."""

    http_method_names = ('post', 'options')
    renderer_classes = (JSONRenderer,)
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsHouseholdParent,)

    def initial(self, request, *args, **kwargs):
        # An unsupported method is refused before authority is considered, so
        # the answer to `GET` never depends on who is asking.
        if request.method.lower() not in self.http_method_names:
            self.http_method_not_allowed(request)
        super().initial(request, *args, **kwargs)

    def get_permission_household(self, request):
        """The one household the caller may act in, or `None`."""
        membership = resolve_active_membership(request.user, request)
        return None if membership is None else membership.household

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            # Re-resolved inside the transaction: a membership revoked a
            # moment ago cannot slip a write through.
            membership = resolve_active_membership(request.user, request)
            if membership is None or membership.role != Membership.Role.PARENT:
                raise PermissionDenied(PERMISSION_DENIED_DETAIL)

            try:
                change_own_password(
                    user=membership.user,
                    household=membership.household,
                    current_password=serializer.validated_data['current_password'],
                    new_password=serializer.validated_data['new_password'],
                )
            except PasswordMismatchError:
                return Response(
                    {'current_password': [PASSWORD_INCORRECT_DETAIL]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except PasswordWeakError as error:
                return Response(
                    {'new_password': error.messages},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            update_session_auth_hash(request._request, membership.user)

        return Response(status=status.HTTP_204_NO_CONTENT)
