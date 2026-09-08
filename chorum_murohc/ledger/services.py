"""Read-only ledger reads: one balance and one history, both household-scoped.

The ledger is the single source of truth for points. There is no denormalised
balance column, no cached total and no stored running sum anywhere: every
figure here is computed from the surviving `LedgerEntry` rows at the moment of
the call, which is what `_docs/retention-policy.md` requires when a member and
their rows are gone.

Both functions filter on the household **and** the user. The schema permits a
user to hold entries in more than one household, so filtering on the user
alone would leak another household's arithmetic into a household-scoped
answer.

Neither function writes, and neither emits an audit event. They live in the
`ledger` package rather than in the API layer because the approved direction
map lets `rewards` and `progression` import `ledger` and forbids any product
package importing the API layer above them, so a helper placed there could
never be reused.
"""

from django.db.models import Sum

from chorum_murohc.ledger.models import LedgerEntry


def entries_for_user(household, user):
    """Every ledger entry belonging to `user` inside `household`."""
    return LedgerEntry.objects.filter(household=household, user=user)


def balance_for_user(household, user):
    """Return the point total `user` holds in `household`.

    A user with no entry has a balance of `0`, never `None`: an empty history
    is a real zero balance rather than a missing answer. The total is a plain
    integer sum of `amount`, so a negative net is returned as it stands and is
    never clamped at zero.
    """
    total = entries_for_user(household, user).aggregate(total=Sum('amount'))['total']
    return 0 if total is None else total


def ledger_history_for_user(household, user):
    """Return `user`'s entries in `household`, newest first.

    The order is stated here rather than inherited from the model `Meta`, so
    that paging cannot start depending on a default another task may change.
    `-created_at, -id` is a total order: two entries sharing a timestamp fall
    back to the descending identifier, so no page boundary can repeat or drop
    a row.
    """
    return entries_for_user(household, user).order_by('-created_at', '-id')
