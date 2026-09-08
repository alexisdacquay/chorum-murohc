"""Set, replace, and verify a parent's approval PIN (T030, issue #30).

Implements the storage and verification half of the approved contract in
`_docs/approval-authentication.md`. This module is the only place that ever
compares a submitted PIN to a stored hash: callers pass the PIN in and get a
result back, never the hash itself, and the raw PIN is never logged, stored,
or placed in an audit event's context (redaction in `audit.models` is
defence in depth, not permission to rely on it here).

Two operations:

- `set_or_replace_pin` creates a parent's first PIN or replaces an existing
  one. It requires the parent's current account password in the same call
  (the approved contract's stand-in for both "set" and "forgot"), rejects a
  weak or repeated value with one generic reason, and writes `pin.set` or
  `pin.change` depending on whether a PIN already existed.
- `verify_pin` checks a submitted PIN against one specific parent's hash,
  scoped to a household the parent must currently hold a live `parent`
  membership in. It enforces the five-attempts-per-fifteen-minutes lockout
  (T033) under a row lock so concurrent attempts cannot lose an increment,
  and writes `pin.verify_failed` and, on the attempt that trips it,
  `pin.locked`. A successful verification writes no event of its own: the
  future decision that consumes it names the verified parent as actor
  instead (`_docs/approval-authentication.md`, "What is said and recorded").

This module has no HTTP endpoint of its own for `verify_pin`: the approval
flow that will call it (T045 to T047) is a later task. The versioned HTTP
API layer's PIN view calls `set_or_replace_pin` only.
"""

import re
from datetime import timedelta
from enum import Enum
from itertools import pairwise

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Membership, ParentPin

PIN_MIN_LENGTH = 4
PIN_MAX_LENGTH = 10

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)

PIN_SET_ACTION = 'pin.set'
PIN_CHANGE_ACTION = 'pin.change'
PIN_VERIFY_FAILED_ACTION = 'pin.verify_failed'
PIN_LOCKED_ACTION = 'pin.locked'

_AUDIT_TARGET_TYPE = 'identity.User'

_PIN_FORMAT = re.compile(rf'\A\d{{{PIN_MIN_LENGTH},{PIN_MAX_LENGTH}}}\Z')

# A small, well-known set of the weakest possible PINs, kept in code rather
# than configuration because it is short and never changes independently of
# this module. It catches the common cases the structural checks below do
# not: a value nobody would call sequential or repetitive but that public PIN
# breach research shows is guessed first regardless.
_BLOCKLIST = frozenset(
    {
        '0000',
        '1111',
        '2222',
        '3333',
        '4444',
        '5555',
        '6666',
        '7777',
        '8888',
        '9999',
        '1004',
        '1212',
        '1313',
        '2001',
        '2000',
        '6969',
        '1122',
        '123456',
        '000000',
        '111111',
    }
)


class PinPasswordError(Exception):
    """The supplied current account password did not match."""


class PinFormatError(Exception):
    """The PIN was not four to ten digits."""


class PinWeakError(Exception):
    """The PIN was refused as too guessable, or matched the current one."""


class PinVerificationResult(Enum):
    """The three outcomes `verify_pin` can return. Nothing else is possible."""

    MATCH = 'match'
    NO_MATCH = 'no_match'
    LOCKED = 'locked'


def _is_repetitive(pin):
    """A PIN built by repeating a short unit: '1111', '1212', '123123'.

    Every period from one up to (but excluding) the full length is tried, so
    this also catches the all-identical case as the period-one instance of
    the same rule rather than as a separate check.
    """
    length = len(pin)
    for period in range(1, length):
        if length % period == 0 and pin == pin[:period] * (length // period):
            return True
    return False


def _is_sequential_run(pin):
    """An ascending or descending run of consecutive digits: '1234', '4321'."""
    digits = [int(character) for character in pin]
    ascending = all(b - a == 1 for a, b in pairwise(digits))
    descending = all(a - b == 1 for a, b in pairwise(digits))
    return ascending or descending


def _is_weak_pin(pin):
    return pin in _BLOCKLIST or _is_repetitive(pin) or _is_sequential_run(pin)


def _write_audit_event(*, household, actor, action, user, context):
    AuditEvent.objects.create(
        household=household,
        actor=actor,
        action=action,
        target_type=_AUDIT_TARGET_TYPE,
        target_id=str(user.pk),
        context=context,
    )


def _has_live_parent_membership(user, household):
    return Membership.objects.filter(
        household=household,
        user=user,
        role=Membership.Role.PARENT,
    ).exists()


def set_or_replace_pin(*, user, household, current_password, new_pin):
    """Set `user`'s first PIN, or replace their existing one.

    `household` is used only to attribute the audit event; the PIN itself
    belongs to the user account, not to a household. Raises `PinPasswordError`
    when `current_password` does not match the account, `PinFormatError` when
    `new_pin` is not four to ten digits, and `PinWeakError` for every refused
    weak value including a resubmission of the current PIN - one exception
    type per the one generic reason the approved contract requires, so a
    caller never has to build a more specific message than "Choose a
    different PIN."
    """
    if not user.check_password(current_password):
        raise PinPasswordError

    if not _PIN_FORMAT.fullmatch(new_pin):
        raise PinFormatError

    with transaction.atomic():
        existing = ParentPin.objects.select_for_update().filter(user=user).first()

        if existing is not None and check_password(new_pin, existing.pin_hash):
            raise PinWeakError
        if _is_weak_pin(new_pin):
            raise PinWeakError

        pin_hash = make_password(new_pin)
        if existing is None:
            ParentPin.objects.create(user=user, pin_hash=pin_hash)
            action = PIN_SET_ACTION
        else:
            existing.pin_hash = pin_hash
            existing.failed_attempts = 0
            existing.locked_until = None
            existing.save(
                update_fields=(
                    'pin_hash',
                    'failed_attempts',
                    'locked_until',
                    'updated_at',
                )
            )
            action = PIN_CHANGE_ACTION

        _write_audit_event(
            household=household,
            actor=user,
            action=action,
            user=user,
            context={},
        )


def verify_pin(*, user, household, submitted_pin):
    """Check `submitted_pin` against `user`'s hash, scoped to `household`.

    Returns `PinVerificationResult.MATCH`, `.NO_MATCH`, or `.LOCKED`. Never
    raises for an ordinary wrong guess, a missing PIN, or a lockout: every one
    of those is exactly the generic outcome the approved contract requires,
    so a caller needs no exception handling to build the one generic response
    a wrong PIN, an unknown parent, a parent with no PIN, and a locked parent
    all share.

    `household` must be a household `user` currently holds a live `parent`
    membership in (re-read here, not trusted from the caller), matching
    "Verification also requires a live parent membership in the submission's
    household, rechecked inside the writing transaction." A mismatch is a
    silent `NO_MATCH`: no counter is touched and no event is written, because
    the mismatch describes the caller's own request, not an attempt against
    this parent's PIN.
    """
    if not _has_live_parent_membership(user, household):
        return PinVerificationResult.NO_MATCH

    with transaction.atomic():
        pin_row = ParentPin.objects.select_for_update().filter(user=user).first()
        if pin_row is None:
            return PinVerificationResult.NO_MATCH

        now = timezone.now()
        if pin_row.locked_until is not None:
            if pin_row.locked_until > now:
                return PinVerificationResult.LOCKED
            # The fifteen minutes have passed: the lock clears, and this
            # attempt starts a fresh window rather than inheriting the old
            # count, exactly as a successful verification or a new PIN does.
            pin_row.failed_attempts = 0
            pin_row.locked_until = None

        if check_password(submitted_pin, pin_row.pin_hash):
            if pin_row.failed_attempts != 0 or pin_row.locked_until is not None:
                pin_row.failed_attempts = 0
                pin_row.locked_until = None
                pin_row.save(
                    update_fields=('failed_attempts', 'locked_until', 'updated_at')
                )
            return PinVerificationResult.MATCH

        pin_row.failed_attempts += 1
        newly_locked = pin_row.failed_attempts >= MAX_FAILED_ATTEMPTS
        if newly_locked:
            pin_row.locked_until = now + LOCKOUT_DURATION
        pin_row.save(update_fields=('failed_attempts', 'locked_until', 'updated_at'))

        _write_audit_event(
            household=household,
            actor=None,
            action=PIN_VERIFY_FAILED_ACTION,
            user=user,
            context={'failed_attempts': pin_row.failed_attempts},
        )
        if newly_locked:
            _write_audit_event(
                household=household,
                actor=None,
                action=PIN_LOCKED_ACTION,
                user=user,
                context={},
            )
        return (
            PinVerificationResult.LOCKED
            if newly_locked
            else PinVerificationResult.NO_MATCH
        )
