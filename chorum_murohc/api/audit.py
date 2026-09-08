"""The parent-only read-only audit endpoint.

One route: `GET /api/v1/audit/`. It lists the caller's own household's
`AuditEvent` rows, newest first, exactly as recorded by the writing side
(`chorum_murohc.audit.models`). This view never creates, edits or removes an
event; the `AuditEvent` model itself already refuses every mutation API after
the initial insert, so there is no update or delete path here to guard.

Scope and authority follow the approved permission matrix in
`_docs/design.md` ("Read audit history"): deny an unauthenticated caller, deny
a child, and allow a parent only the events of the one household their live
membership resolves to. The household is never taken from the client; it
comes from `resolve_active_membership`, exactly as every other endpoint in
this package derives it.

Redaction is not repeated here. `AuditEvent.context` is sanitised once, at
write time, by the model itself (recursive sensitive-key redaction); this
view returns the stored value unchanged; there is no separate
serialization-time filter to keep in sync with the write-side allow-list.

Pagination is DRF's own `PageNumberPagination`, not a hand-rolled scheme, and
is scoped to this view alone: it does not touch the project's shared
`REST_FRAMEWORK` settings, so it cannot change how any other endpoint (for
example the unpaginated chore list) behaves.

Filtering covers exactly the three dimensions the task names: `actor` (a
user id), `action` (an exact action code) and a `date_from`/`date_to` range
over `created_at`. Each is validated before it reaches the database; a
malformed value is a compact 400, never a 500, and an out-of-household actor
id is silently zero rows rather than a distinct error, so a filter can never
be used to probe whether an id belongs to someone else's household.
"""

from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.renderers import JSONRenderer

from chorum_murohc.api.permissions import IsHouseholdParent
from chorum_murohc.api.session import resolve_active_membership
from chorum_murohc.audit.models import AuditEvent

# The one detail returned when the range filter is empty because its two
# ends are the wrong way round. It names neither date.
DATE_RANGE_DETAIL = 'date_from must not be later than date_to.'

# A page small enough to stay readable, a ceiling a query string cannot lift
# past, and an explicit opt-in param name so a caller must ask for a
# different size on purpose.
DEFAULT_PAGE_SIZE = 25
MAXIMUM_PAGE_SIZE = 100
PAGE_SIZE_QUERY_PARAMETER = 'page_size'


class AuditEventPagination(PageNumberPagination):
    """DRF's built-in page-number scheme, sized for this endpoint only."""

    page_size = DEFAULT_PAGE_SIZE
    page_size_query_param = PAGE_SIZE_QUERY_PARAMETER
    max_page_size = MAXIMUM_PAGE_SIZE


class AuditEventSerializer(serializers.ModelSerializer):
    """The exact read shape: no household field, since it is always the
    caller's own and would add nothing a foreign row could ever be compared
    against."""

    class Meta:
        model = AuditEvent
        fields = (
            'id',
            'actor',
            'action',
            'target_type',
            'target_id',
            'created_at',
            'context',
        )
        read_only_fields = fields


class AuditEventFilterSerializer(serializers.Serializer):
    """The exact three query filters this endpoint accepts, and nothing else.

    Any other query parameter is silently ignored, exactly as an unlisted
    field is anywhere else in this project's serializers.
    """

    actor = serializers.IntegerField(required=False, min_value=1)
    action = serializers.CharField(required=False, allow_blank=False, max_length=100)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate(self, attrs):
        date_from = attrs.get('date_from')
        date_to = attrs.get('date_to')
        if date_from is not None and date_to is not None and date_from > date_to:
            raise serializers.ValidationError({'date_to': [DATE_RANGE_DETAIL]})
        return attrs


class AuditEventListView(ListAPIView):
    """`GET /api/v1/audit/`: the caller's own-household audit trail."""

    http_method_names = ('get', 'head', 'options')
    renderer_classes = (JSONRenderer,)
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsHouseholdParent,)
    serializer_class = AuditEventSerializer
    pagination_class = AuditEventPagination

    def initial(self, request, *args, **kwargs):
        # An unsupported method is refused before authority is considered, so
        # the answer to `POST` never depends on who is asking: a parent and a
        # child, authenticated or not, all get the same 405.
        if request.method.lower() not in self.http_method_names:
            self.http_method_not_allowed(request)
        super().initial(request, *args, **kwargs)

    def get_permission_household(self, request):
        """The one household the caller may read, or `None`."""
        membership = resolve_active_membership(request.user)
        return None if membership is None else membership.household

    def get_queryset(self):
        """Every event of the caller's household that matches every filter
        given, newest first (the model's own default ordering).

        Household scoping is applied before any filter, so an `actor` id from
        another household narrows an already-empty set rather than reaching
        across it.
        """
        household = self.get_permission_household(self.request)
        if household is None:
            return AuditEvent.objects.none()

        filters = AuditEventFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        criteria = filters.validated_data

        queryset = AuditEvent.objects.filter(household=household)
        if 'actor' in criteria:
            queryset = queryset.filter(actor_id=criteria['actor'])
        if 'action' in criteria:
            queryset = queryset.filter(action=criteria['action'])
        if 'date_from' in criteria:
            queryset = queryset.filter(created_at__date__gte=criteria['date_from'])
        if 'date_to' in criteria:
            queryset = queryset.filter(created_at__date__lte=criteria['date_to'])
        return queryset
