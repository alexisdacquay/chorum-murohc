"""Level computation and the one-time level-up acknowledgement.

Issue #61's decided policy, in full: a child levels as they earn. The level
is a function of LIFETIME points earned, not the current balance, so
spending never demotes anyone. Ten levels, with these lifetime thresholds:
50, 150, 300, 500, 750, 1050, 1400, 1800, 2250, 2750. Levelling is computed
from the ledger rather than stored as a mutable counter, and the level-up is
shown to the child once, the first time they see it.

Two entry points:

- `progression_for_user` is a pure read: level, the maximum, lifetime points,
  and the remaining distance to the next level (or `None` at the maximum).
  It never writes.
- `acknowledge_level_up` is the one write this package performs: it marks the
  child's current level as shown, exactly once, and emits one `level.up`
  audit event the first time a given level is acknowledged. A repeat call
  once nothing is newly reached changes nothing and emits nothing, matching
  the idempotent-replay rule `api/submissions.py` already sets.

No cost, no spend, no client-supplied level: the client never tells the
server what level it is or should be, only that it has shown the current one.
"""

from django.db import transaction

from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.ledger.services import lifetime_points_earned_for_user
from chorum_murohc.progression.models import MAX_LEVEL, LevelAcknowledgement

# Lifetime points needed to reach level 1, 2, 3, ... in order. Level 0 is
# where every child starts, before earning anything.
LEVEL_THRESHOLDS = (50, 150, 300, 500, 750, 1050, 1400, 1800, 2250, 2750)

assert len(LEVEL_THRESHOLDS) == MAX_LEVEL
assert list(LEVEL_THRESHOLDS) == sorted(LEVEL_THRESHOLDS)

AUDIT_TARGET_TYPE = 'progression'
AUDIT_LEVEL_UP = 'progression.level_up'


def level_for_lifetime_points(lifetime_points):
    """The level `lifetime_points` reaches: the count of thresholds cleared.

    Never negative and never above `MAX_LEVEL`, since `LEVEL_THRESHOLDS` has
    exactly `MAX_LEVEL` entries.
    """
    level = 0
    for threshold in LEVEL_THRESHOLDS:
        if lifetime_points < threshold:
            break
        level += 1
    return level


def _next_level_threshold(level):
    """Lifetime points needed for `level + 1`, or `None` at the maximum."""
    return None if level >= MAX_LEVEL else LEVEL_THRESHOLDS[level]


def progression_for_user(household, user):
    """The caller's own level state, computed fresh. Never writes.

    `points_to_next_level` and `next_level_threshold` are both `None` at the
    maximum: points keep accruing (`lifetime_points` keeps rising) but there
    is nothing further to level into.
    """
    lifetime_points = lifetime_points_earned_for_user(household, user)
    level = level_for_lifetime_points(lifetime_points)
    next_level_threshold = _next_level_threshold(level)
    points_to_next_level = (
        None if next_level_threshold is None else next_level_threshold - lifetime_points
    )
    return {
        'level': level,
        'max_level': MAX_LEVEL,
        'lifetime_points': lifetime_points,
        'next_level_threshold': next_level_threshold,
        'points_to_next_level': points_to_next_level,
    }


def _highest_level_shown(household, user):
    """The stored marker for `user`, or `0` when no row exists yet.

    A missing row means nothing has ever been shown, which is exactly what a
    freshly created row would say, so a plain read never has to create one.
    """
    return (
        LevelAcknowledgement.objects.filter(household=household, user=user)
        .values_list('highest_level_shown', flat=True)
        .first()
        or 0
    )


def pending_level_up_for_user(household, user, state=None):
    """The level to celebrate, or `None` when nothing new has been shown.

    Only the current level is ever offered, never every level skipped along
    the way: a child who earns a large chore credit and jumps two levels at
    once sees one celebration for the level they are now at, not a replay of
    each one passed through.
    """
    state = state or progression_for_user(household, user)
    highest_shown = _highest_level_shown(household, user)
    return state['level'] if state['level'] > highest_shown else None


def progression_summary_for_user(household, user):
    """`progression_for_user` plus `pending_level_up`. Never writes."""
    state = progression_for_user(household, user)
    return {
        **state,
        'pending_level_up': pending_level_up_for_user(household, user, state),
    }


def acknowledge_level_up(household, user):
    """Mark the caller's current level as shown, exactly once.

    Recomputes the level fresh inside the transaction, under a row lock, so a
    chore credited a moment ago is reflected before the marker moves. When
    the stored marker is already at or above the freshly computed level this
    changes nothing and emits nothing: a repeat call, or a call with nothing
    new to show, is a true no-op.

    Returns `(summary, changed)`: `summary` is the same shape
    `progression_summary_for_user` returns (with `pending_level_up` now
    `None` when `changed` is true), and `changed` tells the caller whether an
    audit event was written.
    """
    with transaction.atomic():
        row, _ = LevelAcknowledgement.objects.select_for_update().get_or_create(
            household=household,
            user=user,
        )
        state = progression_for_user(household, user)
        current_level = state['level']

        if current_level <= row.highest_level_shown:
            summary = {**state, 'pending_level_up': None}
            return summary, False

        from_level = row.highest_level_shown
        row.highest_level_shown = current_level
        row.save(update_fields=['highest_level_shown', 'updated_at'])

        AuditEvent.objects.create(
            household=household,
            actor=user,
            action=AUDIT_LEVEL_UP,
            target_type=AUDIT_TARGET_TYPE,
            target_id=str(row.pk),
            context={
                'actor_id': user.pk,
                'from_level': from_level,
                'to_level': current_level,
                'lifetime_points': state['lifetime_points'],
            },
        )

        summary = {**state, 'pending_level_up': None}
        return summary, True
