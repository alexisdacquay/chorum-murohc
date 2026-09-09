"""Parent PIN management: `POST /api/v1/auth/pin/` (T031, issue #30).

One route, one operation. It always sets or replaces the caller's own PIN,
whichever applies: `_docs/approval-authentication.md` makes setting and
changing (and forgetting, which "is the same operation as changing") one
contract, so the interface needs no separate "do I already have a PIN?"
read to choose between two forms, and none is added.

Every write is parent-only, same-origin session authenticated, and
CSRF-protected exactly like every other mutation in this package. The
household and the acting user come from `resolve_active_membership`, re-read
inside the transaction, never from the request body: nothing here lets a
caller name another parent, another household, or a stored PIN or hash back
to itself.

`chorum_murohc.identity.services.set_or_replace_pin` does the real work,
including the audit event; this module's only job is turning its three
exceptions into the compact, generic, secret-safe responses the approved
contract requires. `PinWeakError` and any resubmission of the current PIN
share one identical detail on purpose, so a caller never learns which rule a
refused value tripped.
"""

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
    PIN_MAX_LENGTH,
    PIN_MIN_LENGTH,
    PinFormatError,
    PinPasswordError,
    PinWeakError,
    set_or_replace_pin,
)

# One generic detail per refusal kind, none of which echoes the submitted
# value, the stored hash, or which specific weakness rule fired.
PASSWORD_INCORRECT_DETAIL = 'Enter your current account password correctly.'
PIN_FORMAT_DETAIL = (
    f'PIN must be {PIN_MIN_LENGTH} to {PIN_MAX_LENGTH} digits, numbers only.'
)
PIN_WEAK_DETAIL = 'Choose a different PIN.'


class PinSetSerializer(serializers.Serializer):
    """Exactly the two fields the approved contract requires, both write-only
    so neither can be echoed back in a response or a validation error.

    `pin` allows blank and carries only a generous sanity-cap `max_length`,
    not `PIN_MAX_LENGTH`: the exact four-to-ten-digit rule is one rule, owned
    by `identity.services.set_or_replace_pin`, so a too-short, too-long, or
    non-digit value all reach the same `PinFormatError` and the same
    `PIN_FORMAT_DETAIL` instead of a different message depending on which
    layer happened to notice first.
    """

    current_password = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=False,
        write_only=True,
    )
    pin = serializers.CharField(
        required=True,
        allow_blank=True,
        trim_whitespace=False,
        max_length=1000,
        write_only=True,
    )


class PinView(APIView):
    """`POST /api/v1/auth/pin/`: set or replace the caller's own PIN."""

    http_method_names = ('post', 'options')
    renderer_classes = (JSONRenderer,)
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsHouseholdParent,)

    def initial(self, request, *args, **kwargs):
        # An unsupported method is refused before authority is considered, so
        # the answer to `GET` never depends on who is asking, and no PIN
        # state is ever readable through this route.
        if request.method.lower() not in self.http_method_names:
            self.http_method_not_allowed(request)
        super().initial(request, *args, **kwargs)

    def get_permission_household(self, request):
        """The one household the caller may act in, or `None`."""
        membership = resolve_active_membership(request.user, request)
        return None if membership is None else membership.household

    def post(self, request):
        serializer = PinSetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            # Re-resolved inside the transaction: a membership revoked a
            # moment ago cannot slip a write through.
            membership = resolve_active_membership(request.user, request)
            if membership is None or membership.role != Membership.Role.PARENT:
                raise PermissionDenied(PERMISSION_DENIED_DETAIL)

            try:
                set_or_replace_pin(
                    user=membership.user,
                    household=membership.household,
                    current_password=serializer.validated_data['current_password'],
                    new_pin=serializer.validated_data['pin'],
                )
            except PinPasswordError:
                return Response(
                    {'current_password': [PASSWORD_INCORRECT_DETAIL]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except PinFormatError:
                return Response(
                    {'pin': [PIN_FORMAT_DETAIL]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except PinWeakError:
                return Response(
                    {'pin': [PIN_WEAK_DETAIL]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(status=status.HTTP_204_NO_CONTENT)
