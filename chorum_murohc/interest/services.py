"""Weekly interest accrual: one idempotent ledger credit per user and date.

`_docs/interest-policy.md` is the whole approved policy; this module is its
only write path. `accrue_interest_for_user` re-reads the child's current
membership and ledger balance inside one transaction, calls
`calculator.weekly_interest`, and appends at most one `interest` ledger
entry keyed to the caller-supplied accrual date. Calling it again for the
same user and date is a true no-op: the entry the first call wrote is
returned unchanged and nothing is written twice, which is what lets
`chorum_murohc/interest/management/commands/accrue_interest.py` be run more
than once for the same day (T053's own requirement).

A day with no interest owed - a zero, negative, or sub-threshold balance -
writes nothing at all: `chorum_murohc.ledger.models.LedgerEntry` refuses a
zero amount by database constraint, so there is no such thing as a stored
zero-interest entry, and this module does not try to create one.

Lives in its own package rather than inside `ledger`, matching how
`rewards` and `progression` hold their own ledger-writing services next to
`identity` and `audit` rather than growing `ledger` itself:
`chorum_murohc.interest` may import `identity`, `ledger`, and `audit`
(`_docs/design.md`'s direction map and `chorum_murohc/tests.py`'s enforced
`ALLOWED_DOMAIN_IMPORTS`).
"""

from django.db import transaction

from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Membership
from chorum_murohc.interest.calculator import weekly_interest
from chorum_murohc.ledger.models import LedgerEntry
from chorum_murohc.ledger.services import balance_for_user

# The ledger source this service writes into `LedgerEntry.source_type`,
# matching `rewards.services.LEDGER_SOURCE_TYPE`'s precedent of keeping the
# value next to the one place that writes it.
LEDGER_SOURCE_TYPE = 'interest.accrual'

AUDIT_TARGET_TYPE = 'ledger.LedgerEntry'
AUDIT_ACCRUE = 'interest.accrue'


class InterestAuthorityError(Exception):
    """The named user's current membership in `household` is not a child's.

    The management command's own query already filters to live child
    memberships; this is the same defence-in-depth recheck
    `rewards.services.RewardAuthorityError` applies, so a role changed
    between the command's query and this write fails this one user rather
    than silently paying a parent.
    """


def _idempotency_key(accrual_date):
    return f'interest:{accrual_date.isoformat()}'


def accrue_interest_for_user(*, household, user, accrual_date):
    """Append `user`'s interest for `accrual_date`, or replay a no-op.

    Returns `(entry, created)`:

    - An entry for this user and date already exists: returns
      `(that entry, False)`. Nothing is read or written beyond the lookup.
    - The current balance earns zero interest (at or below zero, or the 2
      percent rounds down to zero): returns `(None, False)`. No entry is
      ever created for a zero amount.
    - Otherwise: appends one `interest` ledger entry, emits one
      `interest.accrue` audit event with `actor=None` (a scheduled job has
      no human actor, matching `_docs/design.md`'s audit contract), and
      returns `(the new entry, True)`.

    Raises `Membership.DoesNotExist` if the membership no longer exists and
    `InterestAuthorityError` if it is no longer a child's. Locks the
    membership row for the duration of the transaction, so two overlapping
    calls for the same user and date serialise rather than racing: the
    second one always sees the first one's committed entry and returns
    `(that entry, False)` instead of attempting a duplicate insert.
    """
    with transaction.atomic():
        membership = Membership.objects.select_for_update().get(
            household=household, user=user
        )
        if membership.role != Membership.Role.CHILD:
            raise InterestAuthorityError

        idempotency_key = _idempotency_key(accrual_date)
        existing = LedgerEntry.objects.filter(
            user=user, idempotency_key=idempotency_key
        ).first()
        if existing is not None:
            return existing, False

        balance = balance_for_user(household, user)
        amount = weekly_interest(balance)
        if amount <= 0:
            return None, False

        entry = LedgerEntry.objects.create(
            household=household,
            user=user,
            amount=amount,
            reason=LedgerEntry.Reason.INTEREST,
            source_type=LEDGER_SOURCE_TYPE,
            source_id=accrual_date.isoformat(),
            idempotency_key=idempotency_key,
        )
        AuditEvent.objects.create(
            household=household,
            actor=None,
            action=AUDIT_ACCRUE,
            target_type=AUDIT_TARGET_TYPE,
            target_id=str(entry.pk),
            context={
                'user_id': user.pk,
                'accrual_date': accrual_date.isoformat(),
                'balance': balance,
                'amount': amount,
            },
        )
        return entry, True


def eligible_children(*, household_id=None):
    """Live, active child memberships, optionally bounded to one household.

    The command's own explicit, bounded scope (`_docs/design.md`: "Trusted
    command or job to household data: use only the named service and its
    explicit bounded scope"). `user__is_active=True` excludes a deactivated
    account exactly as `api/members.py`'s directory listing does; a
    deactivated child keeps every point already earned but accrues no more
    until reactivated.
    """
    memberships = Membership.objects.filter(
        role=Membership.Role.CHILD, user__is_active=True
    ).select_related('household', 'user')
    if household_id is not None:
        memberships = memberships.filter(household_id=household_id)
    return memberships.order_by('household_id', 'user_id')


def preview_interest_for_user(household, user):
    """The amount `accrue_interest_for_user` would credit right now, or 0.

    Read-only: used by the management command's `--dry-run`, so a dry run
    calls the same policy function a real run would rather than
    approximating it.
    """
    return weekly_interest(balance_for_user(household, user))
