"""Redemption endpoints: a child spends points on a reward, and a parent
settles the request.

Three routes under `/api/v1/redemptions/`, same-origin session authenticated
and scoped to the one household the caller is a live member of:

- `GET redemptions/` lists redemptions. A child sees only their own, every
  status, newest first. A parent sees every redemption in the household, the
  same shape plus who asked, so the fulfilment queue and its history are one
  list.
- `POST redemptions/` redeems a reward: debits the points and creates the
  pending row in one transaction. Child only. A repeated `idempotency_key`
  replays the same row instead of charging twice.
- `POST redemptions/<pk>/fulfil/` marks a pending redemption fulfilled.
  Parent only.
- `POST redemptions/<pk>/cancel/` cancels a pending redemption and refunds
  its points in full, as a new ledger entry. Parent only.

All the actual state change, ledger and audit work happens in
`chorum_murohc.rewards.services`, re-validated inside its own transaction
immediately before writing. This module's job is authority, HTTP shape and
mapping the service's outcomes and exceptions onto responses; it holds no
transaction and no ledger write of its own.

A child can never fulfil or cancel: `IsHouseholdParent` denies the two action
routes before either view method runs, exactly as `chores.py` denies write
routes to a child. There is no reject and no reverse: fulfilled is final, and
refusing a pending request is cancelling it.
"""

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
from chorum_murohc.identity.models import Membership
from chorum_murohc.rewards.models import Redemption, Reward
from chorum_murohc.rewards.services import (
    InsufficientPointsError,
    RewardAuthorityError,
    cancel_redemption,
    fulfil_redemption,
    redeem_reward,
)

# The one detail returned when a redemption would take the balance below
# zero. It names no balance and no reward.
INSUFFICIENT_POINTS_DETAIL = 'Not enough points for this reward.'

IDEMPOTENCY_KEY_MAX_LENGTH = 255


IsHouseholdParentOrChild = IsHouseholdParent | IsHouseholdChild


class RedemptionChildSerializer(serializers.ModelSerializer):
    """What a child sees for one of their own redemptions.

    `reward_name` and `reward_points` are the snapshot taken at redemption,
    so this reads correctly even after the catalogue reward is edited or
    removed. There is no live `reward` reference here: a child cannot browse
    to another household's reward through it, and there is nothing to browse
    to once the reward is gone.
    """

    class Meta:
        model = Redemption
        fields = (
            'id',
            'reward_name',
            'reward_points',
            'status',
            'created_at',
            'decided_at',
        )
        read_only_fields = fields


class RedemptionParentSerializer(serializers.ModelSerializer):
    """What a parent sees: the same shape plus who asked."""

    child_id = serializers.IntegerField(read_only=True)
    child_username = serializers.CharField(source='child.username', read_only=True)

    class Meta:
        model = Redemption
        fields = (
            'id',
            'child_id',
            'child_username',
            'reward_name',
            'reward_points',
            'status',
            'created_at',
            'decided_at',
        )
        read_only_fields = fields


class RedemptionWriteSerializer(serializers.Serializer):
    """The only writable body: which reward, and a client-chosen retry key.

    `reward` names the catalogue row by identifier; the service resolves and
    locks it within the caller's own household, so no queryset is built here
    and a foreign or unknown identifier surfaces as the service's own
    `Reward.DoesNotExist`, never a validation error that would confirm or
    deny its existence.
    """

    reward = serializers.IntegerField(min_value=1)
    idempotency_key = serializers.CharField(
        max_length=IDEMPOTENCY_KEY_MAX_LENGTH, allow_blank=False
    )


class _RedemptionAPIView(APIView):
    """Shared authority and HTTP shape for the redemption routes."""

    renderer_classes = (JSONRenderer,)
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsHouseholdParentOrChild,)

    def initial(self, request, *args, **kwargs):
        if request.method.lower() not in self.http_method_names:
            self.http_method_not_allowed(request)
        super().initial(request, *args, **kwargs)

    def get_permission_household(self, request):
        membership = resolve_active_membership(request.user, request)
        return None if membership is None else membership.household


class RedemptionListView(_RedemptionAPIView):
    """`GET /api/v1/redemptions/` and `POST /api/v1/redemptions/`."""

    http_method_names = ('get', 'head', 'post', 'options')

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsHouseholdChild()]
        return [IsHouseholdParentOrChild()]

    def get(self, request):
        membership = resolve_active_membership(request.user, request)
        household = None if membership is None else membership.household
        redemptions = Redemption.objects.filter(household=household)

        if membership is not None and membership.role == Membership.Role.CHILD:
            redemptions = redemptions.filter(child=request.user)
            serializer_class = RedemptionChildSerializer
        else:
            serializer_class = RedemptionParentSerializer

        return Response(serializer_class(redemptions, many=True).data)

    def post(self, request):
        membership = resolve_active_membership(request.user, request)
        if membership is None or membership.role != Membership.Role.CHILD:
            raise PermissionDenied(PERMISSION_DENIED_DETAIL)

        serializer = RedemptionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            redemption, created = redeem_reward(
                household=membership.household,
                child=request.user,
                reward_id=serializer.validated_data['reward'],
                idempotency_key=serializer.validated_data['idempotency_key'],
            )
        except Reward.DoesNotExist:
            raise NotFound() from None
        except (Membership.DoesNotExist, RewardAuthorityError):
            raise PermissionDenied(PERMISSION_DENIED_DETAIL) from None
        except InsufficientPointsError:
            raise serializers.ValidationError(
                {'reward': [INSUFFICIENT_POINTS_DETAIL]}
            ) from None

        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(
            RedemptionChildSerializer(redemption).data, status=response_status
        )


class _RedemptionActionView(_RedemptionAPIView):
    """One parent-only redemption transition, written exactly once."""

    http_method_names = ('post', 'options')
    permission_classes = (IsHouseholdParent,)
    service_fn = None

    def post(self, request, pk):
        membership = resolve_active_membership(request.user, request)
        if membership is None or membership.role != Membership.Role.PARENT:
            raise PermissionDenied(PERMISSION_DENIED_DETAIL)

        try:
            redemption = self.service_fn(
                household=membership.household,
                parent=request.user,
                redemption_id=pk,
            )
        except Redemption.DoesNotExist:
            # Covers missing, foreign-household, and already-decided rows
            # alike: a stale or repeated action is refused the same way a
            # row that never existed is, and neither answer confirms which.
            raise NotFound() from None
        except (Membership.DoesNotExist, RewardAuthorityError):
            raise PermissionDenied(PERMISSION_DENIED_DETAIL) from None

        return Response(RedemptionParentSerializer(redemption).data)


class RedemptionFulfilView(_RedemptionActionView):
    """`POST /api/v1/redemptions/<pk>/fulfil/`."""

    service_fn = staticmethod(fulfil_redemption)


class RedemptionCancelView(_RedemptionActionView):
    """`POST /api/v1/redemptions/<pk>/cancel/`."""

    service_fn = staticmethod(cancel_redemption)
