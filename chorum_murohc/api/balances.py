"""Balance endpoints: the caller's own points and their own ledger history.

Two routes under `/api/v1/`, both same-origin session authenticated, both
read-only, and both scoped to the one household the caller is a live child of:

- `GET balance/` returns exactly `{"balance": <integer>}`, the sum of every
  surviving entry the caller holds in that household.
- `GET ledger/` returns DRF's native page envelope over the same rows, newest
  first, twenty-five to a page.

They are two routes and not one because the balance is a single aggregate over
the whole history: folding it into the first page would make it absent from
the second, and consumers differ, since a screen may poll the scalar without
ever paging the history.

Authority is never taken from the client. The household comes from
`resolve_active_membership`, never from a body, query string, path or header,
so `?user=`, `?child=` and `?household=` are ignored rather than honoured, and
the answer is always the caller's own figures. There is no object lookup, so
there is no object-level household attribute to declare.

This module is child-only and self-only. A parent is denied here, including
their own balance: the permission matrix gives the parent side only the
plan-required household summary and routes it to T084, so a parent-visible
route added here would be a widening the matrix has not approved.

Nothing here writes. No ledger row is created, updated or deleted, and no
audit event is emitted, because reading a balance is not an event.
"""

from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from chorum_murohc.api.permissions import IsHouseholdChild
from chorum_murohc.api.session import resolve_active_membership
from chorum_murohc.ledger.models import LedgerEntry
from chorum_murohc.ledger.services import balance_for_user, ledger_history_for_user

# The only key the balance body carries.
BALANCE_FIELD = 'balance'

# One page of history. There is no client override: a fixed size keeps the
# cost of a page predictable, and widening it later is additive.
HISTORY_PAGE_SIZE = 25

# The one detail returned for a page that does not exist. It repeats neither
# the requested number, the total count nor the underlying exception text.
INVALID_PAGE_DETAIL = 'Invalid page.'


class LedgerHistoryPagination(PageNumberPagination):
    """Native page-number pagination, local to this module.

    It is wired through the view rather than through a global default in
    `config/settings.py`: settings is a shared hotspot this task does not own,
    and the merged chore list deliberately returns a bare array.
    """

    page_size = HISTORY_PAGE_SIZE
    # No `page_size_query_param`, so a caller cannot ask for a larger page.
    invalid_page_message = INVALID_PAGE_DETAIL


class LedgerEntrySerializer(serializers.ModelSerializer):
    """The five fields a history row may show, and nothing else.

    `reason` is the stored code, so a consumer can branch on a stable value,
    and `reason_label` is the model's own display text, so no interface has to
    hard-code English of its own.

    Deliberately absent: `idempotency_key`, a retry key that never leaves the
    server; `household` and `user`, always the caller's own and already in the
    session body; and `source_type` with `source_id`, whose reference format
    belongs to the appending services and is not a contract this task can keep.
    """

    reason_label = serializers.CharField(source='get_reason_display', read_only=True)

    class Meta:
        model = LedgerEntry
        fields = ('id', 'amount', 'reason', 'reason_label', 'created_at')
        read_only_fields = fields


class _BalanceAPIView(APIView):
    """Shared authority and shape for the two read-only balance routes.

    An unsupported method is refused before authority is considered, so the
    answer to `POST` never depends on who is asking and no handler can run for
    a method the route does not define.
    """

    renderer_classes = (JSONRenderer,)
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsHouseholdChild,)
    http_method_names = ('get', 'head', 'options')

    def initial(self, request, *args, **kwargs):
        if request.method.lower() not in self.http_method_names:
            self.http_method_not_allowed(request)
        super().initial(request, *args, **kwargs)

    def get_permission_household(self, request):
        """The one household the caller may read in, or `None`."""
        membership = resolve_active_membership(request.user, request)
        return None if membership is None else membership.household


class BalanceView(_BalanceAPIView):
    """`GET /api/v1/balance/`: the caller's own point total."""

    def get(self, request):
        household = self.get_permission_household(request)
        # Never clamped and never absent: a debited child reads a negative
        # total and a child with no history reads zero.
        balance = balance_for_user(household, request.user)
        return Response({BALANCE_FIELD: balance})


class LedgerHistoryView(_BalanceAPIView):
    """`GET /api/v1/ledger/`: one page of the caller's own history."""

    pagination_class = LedgerHistoryPagination

    def get(self, request):
        household = self.get_permission_household(request)
        entries = ledger_history_for_user(household, request.user)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(entries, request, view=self)
        serializer = LedgerEntrySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
