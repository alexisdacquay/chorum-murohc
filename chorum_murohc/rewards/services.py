"""Write-side reward service: redeem, fulfil, and cancel.

Each function is one atomic transaction. It leaves the `Redemption` row, the
ledger, and the audit trail in agreement, or it changes nothing at all: an
exception raised anywhere inside the `with transaction.atomic()` block rolls
every write in it back, including a row already created earlier in the same
call.

Lives in the `rewards` package rather than in the API layer, matching the
approved direction map in `_docs/design.md`: `rewards` may import `identity`,
`ledger`, and `audit`, and no product package may import the API layer above
it, so a service placed there could never be reused here.

Every function re-resolves and locks its actor's membership and the row it
is about to change inside its own transaction, immediately before writing,
so a membership revoked or a request already decided a moment ago cannot be
overtaken by a race. Locking the acting child's own membership row also
serialises two of that child's own redemption attempts racing for the same
points: the second waits for the first to commit, so it computes the balance
the first attempt actually left behind rather than a stale one both could
otherwise have read as affordable.
"""

from django.db import transaction
from django.utils import timezone

from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Membership
from chorum_murohc.ledger.models import LedgerEntry
from chorum_murohc.ledger.services import balance_for_user
from chorum_murohc.rewards.models import Redemption, Reward

AUDIT_TARGET_TYPE = 'redemption'
AUDIT_REQUEST = 'reward.request'
AUDIT_FULFIL = 'reward.fulfil'
AUDIT_CANCEL = 'reward.cancel'

# The ledger source this service writes into `LedgerEntry.source_type`. Kept
# here, next to the one place that writes it, rather than duplicated at
# each call site.
LEDGER_SOURCE_TYPE = 'rewards.redemption'


class InsufficientPointsError(Exception):
    """The child's spendable balance cannot cover the reward's point cost."""


class RewardAuthorityError(Exception):
    """The re-resolved membership does not hold the role this action needs.

    The API layer already gates every route by role before this module is
    ever called; this is the same defence in depth `chores.py`'s
    `require_parent_membership()` applies, re-checked here, inside the
    locked transaction, immediately before a write.
    """


def _redemption_context(*, actor, redemption, previous_status):
    # `AuditEvent.context` only accepts exact JSON primitive types (see
    # `chorum_murohc/audit/models.py`), and a `TextChoices` member is not
    # exactly `str` even though it behaves like one, so both sides of the
    # transition are coerced to plain strings before they are stored.
    return {
        'actor_id': actor.pk,
        'redemption_id': redemption.pk,
        'reward_id': redemption.reward_id,
        'reward_name': redemption.reward_name,
        'points': redemption.reward_points,
        'status': {
            'before': None if previous_status is None else str(previous_status),
            'after': str(redemption.status),
        },
    }


def redeem_reward(*, household, child, reward_id, idempotency_key):
    """Spend `child`'s points on `reward_id`, or replay an identical retry.

    Returns `(redemption, created)`. `created` is `False` when
    `idempotency_key` already names a redemption this child made: the
    existing row is returned untouched and no second debit is written, so a
    double-tapped button can never charge twice.

    Raises `Reward.DoesNotExist` for a reward that is missing, inactive, or
    in another household, `Membership.DoesNotExist` if the child's own
    membership no longer exists, `RewardAuthorityError` if that membership is
    no longer a child's, and `InsufficientPointsError` when the debit would
    take the balance below zero. Every case leaves the database exactly as it
    was.
    """
    with transaction.atomic():
        membership = Membership.objects.select_for_update().get(
            household=household, user=child
        )
        if membership.role != Membership.Role.CHILD:
            raise RewardAuthorityError()

        existing = Redemption.objects.filter(
            child=child, idempotency_key=idempotency_key
        ).first()
        if existing is not None:
            return existing, False

        reward = Reward.objects.select_for_update().get(
            household=household, pk=reward_id, is_active=True
        )

        if balance_for_user(household, child) < reward.points:
            raise InsufficientPointsError()

        redemption = Redemption.objects.create(
            household=household,
            child=child,
            reward=reward,
            reward_name=reward.name,
            reward_points=reward.points,
            idempotency_key=idempotency_key,
        )
        LedgerEntry.objects.create(
            household=household,
            user=child,
            amount=-reward.points,
            reason=LedgerEntry.Reason.REWARD_DEBIT,
            source_type=LEDGER_SOURCE_TYPE,
            source_id=str(redemption.pk),
            idempotency_key=f'redemption:{redemption.pk}:debit',
        )
        AuditEvent.objects.create(
            household=household,
            actor=child,
            action=AUDIT_REQUEST,
            target_type=AUDIT_TARGET_TYPE,
            target_id=str(redemption.pk),
            context=_redemption_context(
                actor=child, redemption=redemption, previous_status=None
            ),
        )
        return redemption, True


def fulfil_redemption(*, household, parent, redemption_id):
    """Mark a pending redemption fulfilled. No points move: they left the
    balance at request time and a fulfilled redemption is never reversed.

    Raises `Redemption.DoesNotExist` for a row that is missing, in another
    household, or already decided, `Membership.DoesNotExist` if the parent's
    own membership no longer exists, and `RewardAuthorityError` if that
    membership is no longer a parent's.
    """
    with transaction.atomic():
        membership = Membership.objects.select_for_update().get(
            household=household, user=parent
        )
        if membership.role != Membership.Role.PARENT:
            raise RewardAuthorityError()

        redemption = Redemption.objects.select_for_update().get(
            household=household, pk=redemption_id, status=Redemption.Status.PENDING
        )
        previous_status = redemption.status
        redemption.status = Redemption.Status.FULFILLED
        redemption.decided_by = parent
        redemption.decided_at = timezone.now()
        redemption.save()

        AuditEvent.objects.create(
            household=household,
            actor=parent,
            action=AUDIT_FULFIL,
            target_type=AUDIT_TARGET_TYPE,
            target_id=str(redemption.pk),
            context=_redemption_context(
                actor=parent, redemption=redemption, previous_status=previous_status
            ),
        )
        return redemption


def cancel_redemption(*, household, parent, redemption_id):
    """Cancel a pending redemption and refund its points in full.

    The refund is a newly appended, positive `reward_debit` ledger entry,
    never an update or a delete of the original debit: the ledger is
    append-only. Its idempotency key derives from the redemption row, so at
    most one refund can ever exist for it.

    Raises `Redemption.DoesNotExist` for a row that is missing, in another
    household, or already decided, `Membership.DoesNotExist` if the parent's
    own membership no longer exists, and `RewardAuthorityError` if that
    membership is no longer a parent's.
    """
    with transaction.atomic():
        membership = Membership.objects.select_for_update().get(
            household=household, user=parent
        )
        if membership.role != Membership.Role.PARENT:
            raise RewardAuthorityError()

        redemption = Redemption.objects.select_for_update().get(
            household=household, pk=redemption_id, status=Redemption.Status.PENDING
        )
        previous_status = redemption.status
        redemption.status = Redemption.Status.CANCELLED
        redemption.decided_by = parent
        redemption.decided_at = timezone.now()
        redemption.save()

        LedgerEntry.objects.create(
            household=household,
            user=redemption.child,
            amount=redemption.reward_points,
            reason=LedgerEntry.Reason.REWARD_DEBIT,
            source_type=LEDGER_SOURCE_TYPE,
            source_id=str(redemption.pk),
            idempotency_key=f'redemption:{redemption.pk}:refund',
        )
        AuditEvent.objects.create(
            household=household,
            actor=parent,
            action=AUDIT_CANCEL,
            target_type=AUDIT_TARGET_TYPE,
            target_id=str(redemption.pk),
            context=_redemption_context(
                actor=parent, redemption=redemption, previous_status=previous_status
            ),
        )
        return redemption
