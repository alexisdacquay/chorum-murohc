"""Reward-catalogue endpoints: the household's list of rewards a child may
redeem, and its management.

Five routes under `/api/v1/rewards/`, shaped exactly like
`chorum_murohc/api/chores.py`'s chore-pool routes, same-origin session
authenticated and scoped to the one household the caller is a live member of:

- `GET rewards/` lists rewards. A child sees `id`, `name` and `points` for
  the active rewards only. A parent sees the full management shape, active
  by default and both states behind `?include_inactive=true`.
- `POST rewards/` creates a reward. Parent only.
- `GET`, `PATCH` and `DELETE rewards/<pk>/` read, edit and remove one reward.
  Parent only.
- `POST rewards/<pk>/deactivate/` and `POST rewards/<pk>/reactivate/` move a
  reward between the two states. Parent only.

Authority is never taken from the client. The household comes from
`resolve_active_membership`, never from a body, query string, path or
header, and `get_queryset()` filters by it before any lookup, so a reward of
another household is an ordinary generic 404 rather than a denial that
confirms the row exists. Every mutation re-resolves the actor and re-reads
the row inside one transaction, and writes its audit event in that same
transaction.

Redeeming a reward, and a parent's fulfil or cancel of that redemption, are
not here: they read and write the ledger and live in
`chorum_murohc/api/redemptions.py`, on top of `chorum_murohc.rewards.services`.
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
from chorum_murohc.identity.models import Membership
from chorum_murohc.rewards.models import Reward

AUDIT_TARGET_TYPE = 'reward'
AUDIT_CREATE = 'reward.create'
AUDIT_UPDATE = 'reward.update'
AUDIT_DEACTIVATE = 'reward.deactivate'
AUDIT_REACTIVATE = 'reward.reactivate'
AUDIT_DELETE = 'reward.delete'

# The largest value the `points` column can hold. Anything above it is a
# validation error rather than a database error.
POINTS_MAXIMUM = 2147483647

# The one detail returned when a name already exists in the caller's own
# household. It names no other household and echoes no stored row.
DUPLICATE_NAME_DETAIL = 'A reward with this name already exists in this household.'

# The database index behind the case-insensitive per-household name rule. Its
# violation is the same 400 as the serializer's, never a 500.
NAME_UNIQUE_CONSTRAINT = 'reward_hh_name_ci_unique'

# The exact query string that widens a parent list to both states.
INCLUDE_INACTIVE_PARAMETER = 'include_inactive'
INCLUDE_INACTIVE_VALUE = 'true'


# Listing the catalogue is the one route a child shares with a parent.
IsHouseholdParentOrChild = IsHouseholdParent | IsHouseholdChild


def duplicate_name_exists(household, name):
    """Report a reward of `household` whose name matches `name` ignoring case."""
    return Reward.objects.filter(household=household, name__iexact=name).exists()


class RewardChildSerializer(serializers.ModelSerializer):
    """What a child may see: three fields, and never a state or a timestamp."""

    class Meta:
        model = Reward
        fields = ('id', 'name', 'points')
        read_only_fields = fields


class RewardParentSerializer(serializers.ModelSerializer):
    """What a parent may see: the same three fields plus the state and times."""

    class Meta:
        model = Reward
        fields = ('id', 'name', 'points', 'is_active', 'created_at', 'updated_at')
        read_only_fields = fields


class RewardWriteSerializer(serializers.ModelSerializer):
    """The only writable body: exactly a name and a point cost.

    Everything else a caller may send is ignored, so a body carrying
    `household`, `id`, `is_active` or a timestamp cannot place a reward in
    another household, choose its identifier, or bypass the two named state
    actions. The household to check names against arrives in the context, not
    in the body.
    """

    class Meta:
        model = Reward
        fields = ('name', 'points')
        extra_kwargs = {  # noqa: RUF012
            'name': {'required': True, 'allow_blank': False},
            'points': {'required': True, 'min_value': 1, 'max_value': POINTS_MAXIMUM},
        }

    def validate_name(self, value):
        if self.instance is not None and value == self.instance.name:
            return value
        if duplicate_name_exists(self.context['household'], value):
            raise serializers.ValidationError(DUPLICATE_NAME_DETAIL)
        return value


def duplicate_name_error(error):
    """Turn the name index violation into the same 400 the serializer returns."""
    if NAME_UNIQUE_CONSTRAINT not in str(error):
        raise error
    return serializers.ValidationError({'name': [DUPLICATE_NAME_DETAIL]})


class _RewardAPIView(APIView):
    """Shared authority, scoping and audit behaviour for the reward routes."""

    renderer_classes = (JSONRenderer,)
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsHouseholdParent,)
    permission_household_attribute = 'household'

    def initial(self, request, *args, **kwargs):
        if request.method.lower() not in self.http_method_names:
            self.http_method_not_allowed(request)
        super().initial(request, *args, **kwargs)

    def get_permission_household(self, request):
        membership = resolve_active_membership(request.user)
        return None if membership is None else membership.household

    def get_queryset(self):
        household = self.get_permission_household(self.request)
        if household is None:
            return Reward.objects.none()
        return Reward.objects.filter(household=household)

    def require_parent_membership(self):
        membership = resolve_active_membership(self.request.user)
        if membership is None or membership.role != Membership.Role.PARENT:
            raise PermissionDenied(PERMISSION_DENIED_DETAIL)
        return membership

    def get_reward(self, pk, *, lock=False):
        household = self.get_permission_household(self.request)
        rewards = Reward.objects.filter(household=household)
        if lock:
            rewards = rewards.select_for_update()
        reward = rewards.filter(pk=pk).first()
        if reward is None:
            raise NotFound()
        self.check_object_permissions(self.request, reward)
        return reward

    def write_audit_event(self, membership, action, reward_id, context):
        AuditEvent.objects.create(
            household=membership.household,
            actor=membership.user,
            action=action,
            target_type=AUDIT_TARGET_TYPE,
            target_id=str(reward_id),
            context=context,
        )


class RewardListView(_RewardAPIView):
    """`GET /api/v1/rewards/` and `POST /api/v1/rewards/`."""

    http_method_names = ('get', 'head', 'post', 'options')

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsHouseholdParent()]
        return [IsHouseholdParentOrChild()]

    def get(self, request):
        membership = resolve_active_membership(request.user)
        is_parent = membership is not None and membership.role == Membership.Role.PARENT
        rewards = self.get_queryset()

        include_inactive = is_parent and (
            request.query_params.get(INCLUDE_INACTIVE_PARAMETER)
            == INCLUDE_INACTIVE_VALUE
        )
        if not include_inactive:
            rewards = rewards.filter(is_active=True)

        serializer_class = (
            RewardParentSerializer if is_parent else RewardChildSerializer
        )
        return Response(serializer_class(rewards, many=True).data)

    def post(self, request):
        try:
            with transaction.atomic():
                membership = self.require_parent_membership()
                serializer = RewardWriteSerializer(
                    data=request.data,
                    context={'household': membership.household},
                )
                serializer.is_valid(raise_exception=True)
                reward = Reward.objects.create(
                    household=membership.household,
                    name=serializer.validated_data['name'],
                    points=serializer.validated_data['points'],
                    is_active=True,
                )
                self.write_audit_event(
                    membership,
                    AUDIT_CREATE,
                    reward.pk,
                    {
                        'actor_id': membership.user_id,
                        'reward_id': reward.pk,
                        'name': reward.name,
                        'points': reward.points,
                        'is_active': reward.is_active,
                    },
                )
                body = RewardParentSerializer(reward).data
        except IntegrityError as error:
            raise duplicate_name_error(error) from error
        return Response(body, status=status.HTTP_201_CREATED)


class RewardDetailView(_RewardAPIView):
    """`GET`, `PATCH` and `DELETE /api/v1/rewards/<pk>/`, parent only."""

    http_method_names = ('get', 'head', 'patch', 'delete', 'options')

    def get(self, request, pk):
        return Response(RewardParentSerializer(self.get_reward(pk)).data)

    def patch(self, request, pk):
        try:
            with transaction.atomic():
                membership = self.require_parent_membership()
                reward = self.get_reward(pk, lock=True)
                serializer = RewardWriteSerializer(
                    reward,
                    data=request.data,
                    partial=True,
                    context={'household': membership.household},
                )
                serializer.is_valid(raise_exception=True)

                changes = {}
                for field, new_value in serializer.validated_data.items():
                    old_value = getattr(reward, field)
                    if old_value != new_value:
                        changes[field] = {'before': old_value, 'after': new_value}
                        setattr(reward, field, new_value)

                if changes:
                    reward.save(update_fields=(*changes, 'updated_at'))
                    self.write_audit_event(
                        membership,
                        AUDIT_UPDATE,
                        reward.pk,
                        {
                            'actor_id': membership.user_id,
                            'reward_id': reward.pk,
                            'changes': changes,
                        },
                    )
                body = RewardParentSerializer(reward).data
        except IntegrityError as error:
            raise duplicate_name_error(error) from error
        return Response(body)

    def delete(self, request, pk):
        with transaction.atomic():
            membership = self.require_parent_membership()
            reward = self.get_reward(pk, lock=True)
            context = {
                'actor_id': membership.user_id,
                'reward_id': reward.pk,
                'points': reward.points,
                'is_active': reward.is_active,
            }
            reward_id = reward.pk
            reward.delete()
            self.write_audit_event(membership, AUDIT_DELETE, reward_id, context)
        return Response(status=status.HTTP_204_NO_CONTENT)


class _RewardStateView(_RewardAPIView):
    """One parent-only state transition, written exactly once."""

    http_method_names = ('post', 'options')
    target_state = None
    audit_action = None

    def post(self, request, pk):
        with transaction.atomic():
            membership = self.require_parent_membership()
            reward = self.get_reward(pk, lock=True)
            if reward.is_active != self.target_state:
                previous_state = reward.is_active
                reward.is_active = self.target_state
                reward.save(update_fields=('is_active', 'updated_at'))
                self.write_audit_event(
                    membership,
                    self.audit_action,
                    reward.pk,
                    {
                        'actor_id': membership.user_id,
                        'reward_id': reward.pk,
                        'is_active': {
                            'before': previous_state,
                            'after': self.target_state,
                        },
                    },
                )
            body = RewardParentSerializer(reward).data
        return Response(body)


class RewardDeactivateView(_RewardStateView):
    """`POST /api/v1/rewards/<pk>/deactivate/`: take a reward out of use."""

    target_state = False
    audit_action = AUDIT_DEACTIVATE


class RewardReactivateView(_RewardStateView):
    """`POST /api/v1/rewards/<pk>/reactivate/`: put a reward back into use."""

    target_state = True
    audit_action = AUDIT_REACTIVATE
