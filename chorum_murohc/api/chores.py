"""Chore-pool endpoints: the household's list of chores and its management.

Five routes under `/api/v1/chores/`, all same-origin session authenticated and
all scoped to the one household the caller is a live member of:

- `GET chores/` lists chores. A child sees `id`, `name` and `points` for the
  active chores only. A parent sees the full management shape, active by
  default and both states behind `?include_inactive=true`.
- `POST chores/` creates a chore. Parent only.
- `GET`, `PATCH` and `DELETE chores/<pk>/` read, edit and remove one chore.
  Parent only.
- `POST chores/<pk>/deactivate/` and `POST chores/<pk>/reactivate/` move a
  chore between the two states. Parent only.

`PUT` is not offered and `is_active` is never writable through `PATCH`: the two
named actions own that transition, so every audit code stays unambiguous.

Authority is never taken from the client. The household comes from
`resolve_active_membership`, never from a body, query string, path or header,
and `get_queryset()` filters by it before any lookup, so a chore of another
household is an ordinary generic 404 rather than a denial that confirms the row
exists. Every mutation re-resolves the actor and re-reads the row inside one
transaction, and writes its audit event in that same transaction, so a
membership revoked a moment ago cannot slip a write through.

Retention rules come from `_docs/retention-policy.md`: one event per real
mutation, none for a call that changes nothing, and a deletion event that
records counts and identifiers but not the deleted chore's name.
"""

from django.db import IntegrityError, transaction
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from chorum_murohc.api.permissions import (
    PERMISSION_DENIED_DETAIL,
    IsHouseholdChild,
    IsHouseholdParent,
)
from chorum_murohc.api.session import resolve_active_membership
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.chores.models import Chore
from chorum_murohc.identity.models import Membership

# The audit target these endpoints write, and the five codes the retention
# policy lists for a chore.
AUDIT_TARGET_TYPE = 'chore'
AUDIT_CREATE = 'chore.create'
AUDIT_UPDATE = 'chore.update'
AUDIT_DEACTIVATE = 'chore.deactivate'
AUDIT_REACTIVATE = 'chore.reactivate'
AUDIT_DELETE = 'chore.delete'

# The largest value the `points` column can hold. Anything above it is a
# validation error rather than a database error.
POINTS_MAXIMUM = 2147483647

# The one detail returned when a name already exists in the caller's own
# household. It names no other household and echoes no stored row.
DUPLICATE_NAME_DETAIL = 'A chore with this name already exists in this household.'

# The database index behind the case-insensitive per-household name rule. Its
# violation is the same 400 as the serializer's, never a 500.
NAME_UNIQUE_CONSTRAINT = 'chore_hh_name_ci_unique'

# The exact query string that widens a parent list to both states.
INCLUDE_INACTIVE_PARAMETER = 'include_inactive'
INCLUDE_INACTIVE_VALUE = 'true'


# Listing the pool is the one route a child shares with a parent.
IsHouseholdParentOrChild = IsHouseholdParent | IsHouseholdChild


def duplicate_name_exists(household, name):
    """Report a chore of `household` whose name matches `name` ignoring case."""
    return Chore.objects.filter(household=household, name__iexact=name).exists()


class ChoreChildSerializer(serializers.ModelSerializer):
    """What a child may see: three fields, and never a state or a timestamp."""

    class Meta:
        model = Chore
        fields = ('id', 'name', 'points')
        read_only_fields = fields


class ChoreParentSerializer(serializers.ModelSerializer):
    """What a parent may see: the same three fields plus the state and times."""

    class Meta:
        model = Chore
        fields = ('id', 'name', 'points', 'is_active', 'created_at', 'updated_at')
        read_only_fields = fields


class ChoreWriteSerializer(serializers.ModelSerializer):
    """The only writable body: exactly a name and a point value.

    Everything else a caller may send is ignored, so a body carrying
    `household`, `id`, `is_active` or a timestamp cannot place a chore in
    another household, choose its identifier, or bypass the two named state
    actions. The household to check names against arrives in the context, not
    in the body.
    """

    class Meta:
        model = Chore
        fields = ('name', 'points')
        extra_kwargs = {  # noqa: RUF012
            'name': {'required': True, 'allow_blank': False},
            'points': {'required': True, 'min_value': 1, 'max_value': POINTS_MAXIMUM},
        }

    def validate_name(self, value):
        # The value is already trimmed by `CharField`. Leaving the name exactly
        # as stored is not a rename and stays allowed; every other collision
        # with an own-household name, including the same name in another case,
        # is refused so that two chores can never read as the same chore.
        if self.instance is not None and value == self.instance.name:
            return value
        if duplicate_name_exists(self.context['household'], value):
            raise serializers.ValidationError(DUPLICATE_NAME_DETAIL)
        return value


def duplicate_name_error(error):
    """Turn the name index violation into the same 400 the serializer returns.

    A duplicate that slips past the serializer because another request
    committed first is the same product error, so it must not surface as a
    server failure. Any other integrity error is a real fault and is re-raised.
    """
    if NAME_UNIQUE_CONSTRAINT not in str(error):
        raise error
    return serializers.ValidationError({'name': [DUPLICATE_NAME_DETAIL]})


class _ChoreAPIView(APIView):
    """Shared authority, scoping and audit behaviour for the chore routes.

    An unsupported method is refused before authority is considered, so the
    answer to `PUT` never depends on who is asking and no handler can run for
    a method the route does not define.
    """

    renderer_classes = (JSONRenderer,)
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsHouseholdParent,)
    permission_household_attribute = 'household'

    def initial(self, request, *args, **kwargs):
        if request.method.lower() not in self.http_method_names:
            self.http_method_not_allowed(request)
        super().initial(request, *args, **kwargs)

    def get_permission_household(self, request):
        """The one household the caller may act in, or `None`."""
        membership = resolve_active_membership(request.user, request)
        return None if membership is None else membership.household

    def get_queryset(self):
        """Every chore of the caller's household, and nothing else.

        Scoping precedes lookup, so a foreign or unknown identifier is the
        same generic 404 and neither confirms the other.
        """
        household = self.get_permission_household(self.request)
        if household is None:
            return Chore.objects.none()
        return Chore.objects.filter(household=household)

    def require_parent_membership(self):
        """Re-resolve the acting parent, for use inside a write transaction."""
        membership = resolve_active_membership(self.request.user, self.request)
        if membership is None or membership.role != Membership.Role.PARENT:
            raise PermissionDenied(PERMISSION_DENIED_DETAIL)
        return membership

    def get_chore(self, pk, *, lock=False):
        household = self.get_permission_household(self.request)
        chores = Chore.objects.filter(household=household)
        if lock:
            chores = chores.select_for_update()
        chore = chores.filter(pk=pk).first()
        if chore is None:
            raise NotFound()
        # The household of the stored row is checked a second time, so the
        # answer never rests on the query alone.
        self.check_object_permissions(self.request, chore)
        return chore

    def write_audit_event(self, membership, action, chore_id, context):
        AuditEvent.objects.create(
            household=membership.household,
            actor=membership.user,
            action=action,
            target_type=AUDIT_TARGET_TYPE,
            target_id=str(chore_id),
            context=context,
        )


class ChoreListView(_ChoreAPIView):
    """`GET /api/v1/chores/` and `POST /api/v1/chores/`."""

    http_method_names = ('get', 'head', 'post', 'options')

    def get_permissions(self):
        # Reading the pool is the one route both roles hold; creating is the
        # parent's alone, so the row of the matrix is chosen by method.
        if self.request.method == 'POST':
            return [IsHouseholdParent()]
        return [IsHouseholdParentOrChild()]

    def get(self, request):
        membership = resolve_active_membership(request.user, request)
        is_parent = membership is not None and membership.role == Membership.Role.PARENT
        chores = self.get_queryset()

        # A child never sees a deactivated chore, whatever the query string
        # asks for. A parent sees active chores until the filter is explicit.
        include_inactive = is_parent and (
            request.query_params.get(INCLUDE_INACTIVE_PARAMETER)
            == INCLUDE_INACTIVE_VALUE
        )
        if not include_inactive:
            chores = chores.filter(is_active=True)

        serializer_class = ChoreParentSerializer if is_parent else ChoreChildSerializer
        # No pagination: the pool is small and a global default would belong to
        # a task that owns the settings module.
        return Response(serializer_class(chores, many=True).data)

    def post(self, request):
        try:
            with transaction.atomic():
                membership = self.require_parent_membership()
                serializer = ChoreWriteSerializer(
                    data=request.data,
                    context={'household': membership.household},
                )
                serializer.is_valid(raise_exception=True)
                chore = Chore.objects.create(
                    household=membership.household,
                    name=serializer.validated_data['name'],
                    points=serializer.validated_data['points'],
                    is_active=True,
                )
                self.write_audit_event(
                    membership,
                    AUDIT_CREATE,
                    chore.pk,
                    {
                        'actor_id': membership.user_id,
                        'chore_id': chore.pk,
                        'name': chore.name,
                        'points': chore.points,
                        'is_active': chore.is_active,
                    },
                )
                body = ChoreParentSerializer(chore).data
        except IntegrityError as error:
            raise duplicate_name_error(error) from error
        return Response(body, status=status.HTTP_201_CREATED)


class ChoreDetailView(_ChoreAPIView):
    """`GET`, `PATCH` and `DELETE /api/v1/chores/<pk>/`, parent only."""

    http_method_names = ('get', 'head', 'patch', 'delete', 'options')

    def get(self, request, pk):
        return Response(ChoreParentSerializer(self.get_chore(pk)).data)

    def patch(self, request, pk):
        try:
            with transaction.atomic():
                membership = self.require_parent_membership()
                chore = self.get_chore(pk, lock=True)
                serializer = ChoreWriteSerializer(
                    chore,
                    data=request.data,
                    partial=True,
                    context={'household': membership.household},
                )
                serializer.is_valid(raise_exception=True)

                changes = {}
                for field, new_value in serializer.validated_data.items():
                    old_value = getattr(chore, field)
                    if old_value != new_value:
                        changes[field] = {'before': old_value, 'after': new_value}
                        setattr(chore, field, new_value)

                # An edit that changes nothing is not an edit: no write, no
                # new `updated_at`, and no second audit event.
                if changes:
                    chore.save(update_fields=(*changes, 'updated_at'))
                    self.write_audit_event(
                        membership,
                        AUDIT_UPDATE,
                        chore.pk,
                        {
                            'actor_id': membership.user_id,
                            'chore_id': chore.pk,
                            'changes': changes,
                        },
                    )
                body = ChoreParentSerializer(chore).data
        except IntegrityError as error:
            raise duplicate_name_error(error) from error
        return Response(body)

    def delete(self, request, pk):
        with transaction.atomic():
            membership = self.require_parent_membership()
            chore = self.get_chore(pk, lock=True)
            # Counts and identifiers only: the deletion event never records the
            # name of the chore it removed. No submission model exists yet, so
            # the removed count is a constant zero.
            context = {
                'actor_id': membership.user_id,
                'chore_id': chore.pk,
                'points': chore.points,
                'is_active': chore.is_active,
                'submissions_removed': 0,
            }
            chore_id = chore.pk
            chore.delete()
            self.write_audit_event(membership, AUDIT_DELETE, chore_id, context)
        return Response(status=status.HTTP_204_NO_CONTENT)


class _ChoreStateView(_ChoreAPIView):
    """One parent-only state transition, written exactly once."""

    http_method_names = ('post', 'options')
    target_state = None
    audit_action = None

    def post(self, request, pk):
        with transaction.atomic():
            membership = self.require_parent_membership()
            chore = self.get_chore(pk, lock=True)
            # A chore already in the target state is left alone: nothing is
            # written, `updated_at` stands, and no second event is recorded.
            if chore.is_active != self.target_state:
                previous_state = chore.is_active
                chore.is_active = self.target_state
                chore.save(update_fields=('is_active', 'updated_at'))
                self.write_audit_event(
                    membership,
                    self.audit_action,
                    chore.pk,
                    {
                        'actor_id': membership.user_id,
                        'chore_id': chore.pk,
                        'is_active': {
                            'before': previous_state,
                            'after': self.target_state,
                        },
                    },
                )
            body = ChoreParentSerializer(chore).data
        return Response(body)


class ChoreDeactivateView(_ChoreStateView):
    """`POST /api/v1/chores/<pk>/deactivate/`: take a chore out of use."""

    target_state = False
    audit_action = AUDIT_DEACTIVATE


class ChoreReactivateView(_ChoreStateView):
    """`POST /api/v1/chores/<pk>/reactivate/`: put a chore back into use."""

    target_state = True
    audit_action = AUDIT_REACTIVATE
